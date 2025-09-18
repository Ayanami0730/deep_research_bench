import multiprocessing
import json
import os
import time
import argparse
from tqdm import tqdm
from functools import partial
from .io_utils import load_jsonl
from .api import call_model
import platform

prompt_template = """你会看到一个参考资料和一些statement，请你判断对于参考资料来说statement是supported、unsupported、或者unknown，注意：
首先判断参考资料是否存在有效内容，如果参考资料中没有任何有效信息，如"page not found"页面，则认为所有statement的状态都是unknown。
除此之外，参考资料有效的情况下，对于一个statement来说，如果它包含的事实或数据在参考资料中可以全部或部分找到，就认为它是supported的（数据接受四舍五入）；如果statement中所有的事实和数据在参考资料中都找不到，认为它是unsupported的。

你应该返回json列表格式，列表中的每一项包含statement的序号和判断结果，例如：
[
    {{
        "idx": 1,
        "result": "supported"
    }},
    {{
        "idx": 2,
        "result": "unsupported"
    }}
]

下面是参考资料和statements：
<reference>
{reference}
</reference>

<statements>
{statements}
</statements>

下面开始判断，直接输出json列表，不要输出任何闲聊或解释。"""

prompt_template_en = """You will be provided with a reference and some statements. Please determine whether each statement is 'supported', 'unsupported', or 'unknown' with respect to the reference. Please note:
First, assess whether the reference contains any valid content. If the reference contains no valid information, such as a 'page not found' message, then all statements should be considered 'unknown'.
If the reference is valid, for a given statement: if the facts or data it contains can be found entirely or partially within the reference, it is considered 'supported' (data accepts rounding); if all facts and data in the statement cannot be found in the reference, it is considered 'unsupported'.

You should return the result in a JSON list format, where each item in the list contains the statement's index and the judgment result, for example:
[
    {{
        "idx": 1,
        "result": "supported"
    }},
    {{
        "idx": 2,
        "result": "unsupported"
    }}
]

Below are the reference and statements:
<reference>
{reference}
</reference>

<statements>
{statements}
</statements>

Begin the assessment now. Output only the JSON list, without any conversational text or explanations."""


def validate(data, id_to_lang_map):
    url = data[0]
    ref = data[1]['url_content']
    facts = data[1]['facts']
    article_id = data[1].get('article_id')

    if ref is None:
        return {
            "url": url,
            "validate_res": [],
            "error": "no reference"
        }
    
    # Determine language based on article ID
    if not article_id:
        error_msg = "Article ID not provided for language determination"
        print(error_msg)
        return {
            "url": url,
            "validate_res": [],
            "error": error_msg
        }
    
    if article_id not in id_to_lang_map:
        error_msg = f"Language not found for article ID: {article_id}"
        print(error_msg)
        return {
            "url": url,
            "validate_res": [],
            "error": error_msg
        }
    
    lang = id_to_lang_map[article_id]
    
    facts_str = '\n'.join([f"{i+1}. {fact}" for i, fact in enumerate(facts)])

    if lang == "zh":
        user_prompt = prompt_template.format(reference=ref, statements=facts_str)
    elif lang == "en":
        user_prompt = prompt_template_en.format(reference=ref, statements=facts_str)
    else:
        error_msg = f"Unsupported language: {lang}"
        print(error_msg)
        return {
            "url": url,
            "validate_res": [],
            "error": error_msg
        }
    
    retries = 0
    error = None
    while retries < 3:
        try:
            response = call_model(user_prompt)

            validate_res = json.loads(response.replace("```json", "").replace("```", ""))
            for _v in validate_res:
                _v['idx'] -= 1
            assert len(validate_res) == len(facts)

            return {
                "url": url,
                "validate_res": validate_res,
                "error": None
            }
        except Exception as e:
            error = str(e)
            time.sleep(3)
            retries += 1
    
    return {
        "url": url,
        "validate_res": [],
        "error": error
    } 


def validate_all(
    output_path: str,
    raw_data_path: str,
    query_data_path: str,
    n_total_process: int
) -> list:
    raw_data = load_jsonl(raw_data_path)
    results = []

    # Load the query data to get language information
    query_data = load_jsonl(query_data_path)

    # Create a mapping from ID to language
    id_to_lang_map = {
        item['id']: item.get('language')
        for item in query_data
        if 'id' in item and 'language' in item
    }

    if not id_to_lang_map:
        raise ValueError("No valid language information found in query data")

    # if the output file exists, load the processed ids and filter out the processed instances
    if os.path.exists(output_path):
        processed = [d['id'] for d in load_jsonl(output_path)]
        data_to_process = [d for d in raw_data if d['id'] not in processed]
    else:
        data_to_process = raw_data

    print(f"Processing {len(data_to_process)} instances...")

    for d in tqdm(data_to_process):
        # get the citations that need to be validated
        citations = [(k, v) for k, v in d['citations_deduped'].items()]

        # Add article_id to each citation's value for language determination
        article_id = d.get('id')
        if not article_id:
            print(f"Warning: Article has no ID field, skipping validation")
            continue

        for citation in citations:
            citation[1]['article_id'] = article_id

        if n_total_process == 1:
            results = [validate(citation, id_to_lang_map) for citation in citations]
        elif n_total_process > 1:
            run_partial = partial(validate, id_to_lang_map=id_to_lang_map)
            with multiprocessing.Pool(processes=n_total_process) as pool:
                results = pool.map(run_partial, citations)

        for res in results:
            d['citations_deduped'][res['url']]['validate_res'] = res['validate_res']
            d['citations_deduped'][res['url']]['validate_error'] = res['error']

        with open(output_path, 'a+', encoding='utf-8') as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    return results


if __name__ == '__main__':
    if platform.system() == 'Darwin':
        try:
            multiprocessing.set_start_method('spawn')
        except RuntimeError:
            pass
    else:
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--raw_data_path", type=str, required=True)
    parser.add_argument("--query_data_path", type=str, required=True, help="Path to query data with language information")
    parser.add_argument("--n_total_process", type=int, default=1)
    args = parser.parse_args()

    validate_all(
        output_path=args.output_path,
        raw_data_path=args.raw_data_path,
        query_data_path=args.query_data_path,
        n_total_process=args.n_total_process,
    )

