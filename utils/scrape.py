import multiprocessing
import json
import os
import time
import argparse
import platform
from tqdm import tqdm
from .api import scrape_url
from .io_utils import load_jsonl


def scrape(citation_url):
    retries = 0
    while retries < 3:
        result = scrape_url(citation_url)
        retries += 1
        if 'error' in result:
            time.sleep(1)
        else:
            break

    url_content = None
    if 'error' not in result:
        title = result.get('title', '')
        content = result.get('content', '')
        description = result.get('description', '')

        url_content = f"{title}\n\n{description}\n\n{content}"
    else:
        url_content = f"scrape failed: {result.get('error', 'unknown error')}"
    # print(f"url_content: {url_content}")
    return {
        'url': citation_url,
        'url_content': url_content
    } 


if __name__ == '__main__':
    if platform.system() in {'Darwin', 'Windows'}:
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
    parser.add_argument("--n_total_process", type=int, default=1)
    args = parser.parse_args()
    
    output_path = args.output_path
    
    # initialize variables
    raw_data = []
    data_to_process = []
    processed = []
    
    try:
        raw_data = load_jsonl(args.raw_data_path)
        
        if os.path.exists(output_path):
            processed = [d['id'] for d in load_jsonl(output_path)]
            data_to_process = [d for d in raw_data if d['id'] not in processed]
        else:
            data_to_process = raw_data
    except:
        import sys
        print(f"cannot process file {args.raw_data_path}")
        sys.exit(f'{args.raw_data_path} has not been processed yet...')
    
    print(f"processing {len(data_to_process)} instances...")

    for d in tqdm(data_to_process):
        # get the citations that need to be scraped
        citations = list([k for k, v in d['citations_deduped'].items() if 'url_content' not in v or not v['url_content']])
        results = []

        n_total_process = min(args.n_total_process, len(citations))

        if n_total_process == 1:
            results = [scrape(citation) for citation in citations]
        elif n_total_process > 1:
            try:
                with multiprocessing.Pool(processes=n_total_process) as pool:
                    results = pool.map(scrape, citations)
            except KeyboardInterrupt:
                print("scrape process interrupted")
                continue
            except Exception as e:
                print(f"scrape process error: {e}")
                # if error, try using single process
                results = [scrape(citation) for citation in citations]

        # update the url_content
        for res in results:
            d['citations_deduped'][res['url']]['url_content'] = res['url_content']

        # write the updated data to the output file
        with open(output_path, 'a+', encoding='utf-8') as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
