import os
import argparse
from utils import load_jsonl
from tqdm import tqdm

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", type=str, required=True)
    parser.add_argument("--output_path", type=str, required=True)
    args = parser.parse_args()

    total_citations = 0
    total_valid_citations = 0
    total_num = 0
    total_usage = [0, 0]

    data = load_jsonl(args.input_path)

    for d in tqdm(data):
        if not d['citations']:
            continue
        for c in d['citations_deduped'].values():
            if c['validate_error'] is not None:
                continue
            for _c in c['validate_res']:
                if _c['result'] != 'unknown':
                    total_citations += 1
                    if _c['result'] == 'supported':
                        total_valid_citations += 1


        total_num += 1



    avg_total_citations = (total_citations / total_num) if total_num else 0.0
    avg_total_valid_citations = (total_valid_citations / total_num) if total_num else 0.0
    valid_rate = (total_valid_citations / total_citations) if total_citations else 0.0

    with open(args.output_path, 'w', encoding='utf-8') as f:
        f.write(f'total_citations: {avg_total_citations}\n')
        f.write(f'total_valid_citations: {avg_total_valid_citations}\n')
        f.write(f'valid_rate: {valid_rate}\n')
