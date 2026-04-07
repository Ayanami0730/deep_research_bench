import multiprocessing
import json
import os
import argparse
import platform
from functools import partial
from .io_utils import load_jsonl
from .api import call_model


prompt_template = """你会看到一个statement列表，你需要对其去重，并返回去重后的statement序号列表，注意：只有表达完全一致的事情时，两个statement才被认为是重复的，如果列表中没有重复的statement，则返回完整的列表。

你应该返回一个List(int)，列表中的每一项是去重后留下的，不重复的statement的序号，例如：
[1, 3, 5]

下面是你需要去重的statement列表
{statements}

下面开始提取，直接输出整数列表，不要输出任何闲聊或解释。"""


prompt_template_en = """You will be given a list of statements. You need to de-duplicate them and return a list of indices of the unique statements. Note: Two statements are considered duplicates only if they express *exactly the same thing*. If there are no duplicate statements in the list, return the complete list of indices.

You should return a List(int), where each item in the list is the index of a unique, non-duplicated statement that has been retained. For example:
[1, 3, 5]

Below is the list of statements you need to de-duplicate:
{statements}

Please begin the extraction now. Output only the integer list, without any conversational text or explanations."""


def run(data, output_path, id_to_lang_map):
    for i, d in enumerate(data):
        # if the citations extraction failed, skip the instance
        if d['citations'] == "extraction failed":
            print(f">>>>>>>>>> skipped {d['id']}-th instance...")
            continue
        # if there is no citation, skip the instance
        elif not d['citations']:
            d['citations_deduped'] = {}

            with open(output_path, "a+", encoding='utf-8') as f:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
            print(f">>>>>>>>>> generating {d['id']}-th instance...")
            continue
            
        # aggregate the citations by url
        citations = d['citations']
        citation_groups = {}
        for _c in citations:
            if _c['url'] not in citation_groups:
                citation_groups[_c['url']] = []
            citation_groups[_c['url']].append(_c)

        citations_groups_deduped = {}

        # Determine the language based on the id in the query data
        article_id = d.get('id')
        
        if not article_id:
            print(f"Article has no ID field, skipping deduplication")
            continue
            
        if article_id not in id_to_lang_map:
            print(f"Language not found for article ID: {article_id}")
            continue
            
        lang = id_to_lang_map[article_id]
        if lang not in ["zh", "en"]:
            print(f"Unsupported language: {lang} for article ID: {article_id}")
            continue

        # deduplicate the citations by url
        for ref_idx, group in citation_groups.items():
            if len(group) == 1:
                citations_groups_deduped[group[0]['url']] = {
                    'facts': [group[0]['fact']],
                    'url_content': None
                }
                continue

            statements = '\n'.join([f'{i+1}. {_c["fact"]}' for i, _c in enumerate(group)])

            # select the prompt based on the language
            if lang == "zh":
                user_prompt = prompt_template.format(statements=statements)
            elif lang == 'en':
                user_prompt = prompt_template_en.format(statements=statements)
            
            retries = 0

            deduped_idx = []
            while retries < 3:
                retries += 1
                try:
                    response = call_model(user_prompt)
                    deduped_idx = json.loads(response.replace("```json", "").replace("```", ""))

                    break
                except Exception as e:
                    print(repr(e))
                    continue
            
            # if the model failed to deduplicate, use the default deduplication
            if not deduped_idx or 0 in deduped_idx or len(deduped_idx) > len(group):
                deduped_idx = [i+1 for i in range(len(group))]

            # deduplicate the citations by url
            citations_groups_deduped[group[0]['url']] = {
                'facts': [group[i-1]['fact'] for i in deduped_idx],
                'url_content': None
            }

        d['citations_deduped'] = citations_groups_deduped

        with open(output_path, "a+", encoding='utf-8') as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

        print(f">>>>>>>>>> generating {d['id']}-th instance...") 

if __name__ == '__main__':

    if platform.system() in {"Windows", "Darwin"}:
        method = "spawn"
    else:
        method = "fork"
    try:
        multiprocessing.set_start_method(method)
    except RuntimeError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--raw_data_path", type=str, required=True)
    parser.add_argument("--query_data_path", type=str, required=True, help="Path to query data with language information")
    parser.add_argument("--n_total_process", type=int, default=1)
    args = parser.parse_args()
    
    output_path = args.output_path
    raw_data = load_jsonl(args.raw_data_path)
    
    # Load the query data to get language information
    query_data = load_jsonl(args.query_data_path)
    
    # Create a mapping from ID to language
    id_to_lang_map = {item['id']: item.get('language') for item in query_data if 'id' in item and 'language' in item}
    
    if not id_to_lang_map:
        raise ValueError("No valid language information found in query data")

    # if the output file exists, load the processed ids and filter out the processed instances
    if os.path.exists(output_path):
        processed = [d['id'] for d in load_jsonl(output_path)]
        data_to_process = [d for d in raw_data if d['id'] not in processed]
    else:
        data_to_process = raw_data

    print(f"Processing {len(data_to_process)} instances...")

    n_total_process = args.n_total_process
    if n_total_process == 1:
        run(data_to_process, output_path, id_to_lang_map)
    elif n_total_process > 1:
        part_size = (len(data_to_process) + n_total_process - 1) // n_total_process
        data_splits = [data_to_process[i * part_size : (i + 1) * part_size] for i in range(n_total_process)]
        run_partial = partial(run, output_path=output_path, id_to_lang_map=id_to_lang_map)
        with multiprocessing.Pool(processes=n_total_process) as pool:
            results = pool.map(run_partial, data_splits)
