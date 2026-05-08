import json

def load_jsonl(file_path):
    data = []
    with open(file_path, 'r', encoding="utf-8") as f:
        for line in f.readlines():
            data.append(json.loads(line.strip()))
    return data 