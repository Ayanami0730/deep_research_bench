#!/usr/bin/env python3
"""
run_deepnews.py — Generate DeepResearch Bench outputs with the AskNews DeepNews agent.

Reads the benchmark queries, runs each through `sdk.chat.get_deep_news`, extracts the
final report (stripping agent reasoning / <final_answer> tags), and writes the
JSONL format DeepResearch Bench expects:

    {"id": <int>, "prompt": "<original query>", "article": "<report with citations>"}

Output goes to  data/test_data/raw_data/<model_tag>.jsonl  (same dir DRB scores from).

Resumable: re-running skips ids already present in the output file (use --force to redo).

Examples
--------
  # quick 2-task smoke test (1 en + 1 zh), cheap
  python run_deepnews.py --ids 1,51

  # 10 English tasks only
  python run_deepnews.py --limit 10 --only-en

  # full run, opus, deeper research, 5 concurrent
  python run_deepnews.py --model claude-opus-4-6 --max-depth 8 --workers 5

Then set  TARGET_MODELS=("<tag>")  in run_benchmark.sh and `bash run_benchmark.sh`.

Env
---
  ASKNEWS_API_KEY   AskNews API key (required). Read from the environment or a
                    .env file at the repo root (see .env.example).
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from asknews_sdk import AskNewsSDK

# --- paths (resolved relative to this file so cwd doesn't matter) ---
ROOT = Path(__file__).resolve().parent
QUERY_FILE = ROOT / "data" / "prompt_data" / "query.jsonl"
RAW_DATA_DIR = ROOT / "data" / "test_data" / "raw_data"
ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path):
    """Minimal .env loader (no external dep): KEY=VALUE lines, '#' comments,
    does not override variables already set in the real environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def parse_args():
    p = argparse.ArgumentParser(
        description="Run DeepNews over DeepResearch Bench queries.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # task selection
    p.add_argument("-n", "--limit", type=int, default=None,
                   help="Number of tasks to run (after language filter). Default: all 100.")
    p.add_argument("--ids", type=str, default=None,
                   help="Comma-separated task ids to run (overrides --limit / language filters).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--only-en", action="store_true", help="Only English tasks.")
    g.add_argument("--only-zh", action="store_true", help="Only Chinese tasks.")
    # DeepNews config
    p.add_argument("--model", default="claude-sonnet-4-6", help="DeepNews model under test.")
    p.add_argument("--engine", default="v1.5", choices=["v1", "v1.5", "v2.0"])
    p.add_argument("--search-depth", type=int, default=2, help="Minimum research levels.")
    p.add_argument("--max-depth", type=int, default=6, help="Maximum research depth.")
    p.add_argument("--max-parallel-tool-calls", type=int, default=4)
    p.add_argument("--sources", default="asknews,google,wiki,x",
                   help="Comma-separated source list.")
    p.add_argument("--max-tokens", type=int, default=32000,
                   help="Output token cap (SDK default 9999 truncates deep reports).")
    # run control
    p.add_argument("--workers", type=int, default=4, help="Concurrent DeepNews calls.")
    p.add_argument("--retries", type=int, default=3, help="Retries per task on failure.")
    p.add_argument("--model-tag", default=None,
                   help="Output filename stem. Default: deepnews-<engine>-<model>-d<max_depth>.")
    p.add_argument("--force", action="store_true", help="Re-run tasks even if already in output.")
    p.add_argument("--min-chars", type=int, default=500,
                   help="Reject articles shorter than this (treated as failure).")
    return p.parse_args()


def load_queries():
    if not QUERY_FILE.exists():
        sys.exit(f"Query file not found: {QUERY_FILE}")
    return [json.loads(l) for l in QUERY_FILE.open(encoding="utf-8") if l.strip()]


def select_tasks(tasks, args):
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",") if x.strip()}
        return [t for t in tasks if t["id"] in wanted]
    if args.only_en:
        tasks = [t for t in tasks if t.get("language") == "en"]
    elif args.only_zh:
        tasks = [t for t in tasks if t.get("language") == "zh"]
    tasks = sorted(tasks, key=lambda t: t["id"])
    if args.limit is not None:
        tasks = tasks[: args.limit]
    return tasks


def extract_report(full: str) -> str:
    """Pull the report out of the raw stream: prefer the last <final_answer> block;
    otherwise strip the agent preamble up to the first markdown heading. Citations
    (markdown links) are left untouched."""
    blocks = re.findall(r"<final_answer>(.*?)</final_answer>", full, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    m = re.search(r"^#{1,6}\s", full, re.MULTILINE)
    return (full[m.start():] if m else full).strip()


def done_ids(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    ids = set()
    for line in out_path.open(encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                ids.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return ids


def make_runner(sdk, args):
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    def run_one(task):
        last_err = None
        for attempt in range(1, args.retries + 1):
            try:
                parts = []
                resp = sdk.chat.get_deep_news(
                    messages=[{"role": "user", "content": task["prompt"]}],
                    stream=True,
                    model=args.model,
                    engine=args.engine,
                    search_depth=args.search_depth,
                    max_depth=args.max_depth,
                    max_parallel_tool_calls=args.max_parallel_tool_calls,
                    sources=sources,
                    inline_citations="markdown_link",
                    append_references=True,
                    return_sources=True,
                    asknews_watermark=False,
                    max_tokens=args.max_tokens,
                )
                for msg in resp:
                    choices = getattr(msg, "choices", None)  # source objects have none
                    if not choices:
                        continue
                    content = getattr(choices[0].delta, "content", None)
                    if content:
                        parts.append(content)
                article = extract_report("".join(parts))
                if len(article) < args.min_chars:
                    raise RuntimeError(f"article too short ({len(article)} chars)")
                if "http" not in article:
                    raise RuntimeError("no citation URLs in article")
                return {"id": task["id"], "prompt": task["prompt"], "article": article}
            except Exception as e:  # noqa: BLE001 — log and retry transient failures
                last_err = e
                if attempt < args.retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"id={task['id']} failed after {args.retries} tries: {last_err}")

    return run_one


def main():
    args = parse_args()
    load_dotenv(ENV_FILE)

    tag = args.model_tag or f"deepnews-{args.engine}-{args.model}-d{args.max_depth}"
    out_path = RAW_DATA_DIR / f"{tag}.jsonl"
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    tasks = select_tasks(load_queries(), args)
    already = set() if args.force else done_ids(out_path)
    pending = [t for t in tasks if t["id"] not in already]

    print(f"Output : {out_path}")
    print(f"Model  : {args.model}  engine={args.engine}  depth={args.search_depth}..{args.max_depth}")
    print(f"Tasks  : {len(tasks)} selected, {len(already & {t['id'] for t in tasks})} already done, "
          f"{len(pending)} to run  (workers={args.workers})")
    if not pending:
        print("Nothing to do.")
        return

    api_key = os.environ.get("ASKNEWS_API_KEY")
    if not api_key:
        sys.exit("ASKNEWS_API_KEY not set. Export it or add it to a .env file at the repo "
                 "root (see .env.example).")
    sdk = AskNewsSDK(api_key=api_key, scopes=["chat", "news", "stories"])
    run_one = make_runner(sdk, args)

    lock = threading.Lock()
    write_f = out_path.open("a", encoding="utf-8")
    ok = fail = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_one, t): t for t in pending}
            for fut in as_completed(futs):
                tid = futs[fut]["id"]
                try:
                    rec = fut.result()
                    with lock:
                        write_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        write_f.flush()
                    ok += 1
                    print(f"  ✓ {tid:>3}  ({len(rec['article'])} chars)  [{ok+fail}/{len(pending)}]")
                except Exception as e:  # noqa: BLE001
                    fail += 1
                    print(f"  ✗ {tid:>3}  {e}  [{ok+fail}/{len(pending)}]")
    finally:
        write_f.close()

    print(f"\nDone. {ok} ok, {fail} failed. Total in file: {len(done_ids(out_path))}/100")
    if fail:
        print("Re-run the same command to retry failed tasks (they were not written).")
    print(f"\nNext: set  TARGET_MODELS=(\"{tag}\")  in run_benchmark.sh, then `bash run_benchmark.sh`.")


if __name__ == "__main__":
    main()
