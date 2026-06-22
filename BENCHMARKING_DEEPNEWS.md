# Benchmarking DeepNews on DeepResearch Bench

How to evaluate AskNews' **DeepNews** agent on **DeepResearch Bench (DRB)** and get a comparable score.

---

## 1. How the two pieces fit together

DeepResearch Bench is **bring-your-own-output**. It does *not* call your agent. The flow is:

```
query.jsonl (100 tasks)  ──►  YOUR runner calls DeepNews  ──►  raw_data/<model>.jsonl
                                                                      │
                                                                      ▼
                                                            run_benchmark.sh
                                                          ┌───────────┴───────────┐
                                                       RACE judge              FACT pipeline
                                                     (GPT-5.5, report       (extract citations →
                                                      quality vs ref)        dedup → Jina scrape →
                                                                             validate support)
                                                          └───────────┬───────────┘
                                                              race_result.txt / fact_result.txt
```

Our only real work is the **runner**: take the 100 benchmark prompts, run each through DeepNews, and emit one JSONL line per task in the exact shape DRB expects. Everything after that is the upstream eval harness, unchanged.

### What DRB requires of each output line
`data/test_data/raw_data/<model_name>.jsonl`, one JSON object per line:
```json
{"id": 1, "prompt": "<original query text>", "article": "<full report WITH inline citations>"}
```
- `id` and `prompt` must match `data/prompt_data/query.jsonl` (100 tasks: 50 zh + 50 en, across 22 topics).
- `article` is the final report. **Inline citations with real URLs are mandatory** — the FACT pipeline extracts statement→URL pairs from the article body and scrapes each URL to verify support. No URLs in the body ⇒ FACT score ≈ 0.

### What the two scores measure
- **RACE** — report quality (Comprehensiveness, Insight/Depth, Instruction-Following, Readability), judged by GPT-5.5 against a reference report, with task-adaptive weights.
- **FACT** — Citation Accuracy (% of citations whose source actually supports the claim) and Effective Citations (avg # of verifiably-supported citations per task).

---

## 2. The DeepNews call

DeepNews is OpenAI-compatible (`POST /v1/chat/deepnews`), exposed through the SDK as `sdk.chat.get_deep_news(...)`. The runner (§3) calls it like this:

```python
from asknews_sdk import AskNewsSDK

sdk = AskNewsSDK(api_key="...", scopes=["chat", "news", "stories"])

response = sdk.chat.get_deep_news(
    messages=[{"role": "user", "content": prompt}],
    stream=True,
    engine="v1.5",                  # parallel tool calling + improved research
    model="claude-sonnet-4-6",      # judged report — keep fixed across the run
    search_depth=2,                 # min research levels
    max_depth=6,                    # max research depth (depth↑ = quality↑, cost/time↑)
    max_parallel_tool_calls=4,
    sources=["asknews", "google", "wiki", "x"],
    inline_citations="markdown_link",  # FACT-compatible citations (SDK default)
    append_references=True,            # references section (SDK default)
    asknews_watermark=False,           # keep the watermark out of the judged report
    max_tokens=32000,                  # SDK default 9999 truncates deep reports
    return_sources=True,
)
for msg in response:                   # stream yields content chunks AND source objects
    choices = getattr(msg, "choices", None)   # source objects have no .choices
    if choices and choices[0].delta.content:
        print(choices[0].delta.content, end="", flush=True)
```

**Citations — already handled, no engineering needed.** DeepNews emits inline citations as markdown links wrapped in brackets, e.g. `...20% of the world's oil [[PN](http://www.theportugalnews.com/...)][[TI](https://timesofindia.../...)]`. DRB's FACT extractor (`utils/extract.py`) *natively* parses this: its accepted citation form #4 is exactly `[Citation Source](Citation Link)`, matched by the regex `\[([^\]]+)\]\(([^)]+)\)` (the outer bracket of `[[PN](url)]` is harmless; the inner `[PN](url)` is what matches; `ref_idx` is set to `0` for this form). So the URLs DeepNews already produces flow straight into FACT verification — **no prompt-wrapping or reference reconciliation required.**

**The actual preprocessing requirement — extract the report from the stream.** A real DeepNews response is not pure report text. It contains:
1. **Agent preamble / reasoning chatter** before the report — e.g. *"I now have sufficient information to provide a comprehensive answer. Let me compile everything."*
2. The report itself wrapped in **`<final_answer> ... </final_answer>`** tags.
3. Sometimes a repeat of (1) between multiple `<final_answer>` blocks if the agent iterates.

The `article` field must contain **only the final report body** — strip the preamble and the `<final_answer>` tags. If chatter leaks in: FACT extraction wastes calls on URL-free narration (minor), but RACE's Readability/Instruction-Following scores suffer (the judge sees meta-commentary that isn't part of the report). Extraction logic:
- Capture the content of the **last** `<final_answer>...</final_answer>` block (the agent's final compiled answer). Regex: `re.findall(r"<final_answer>(.*?)</final_answer>", full, re.DOTALL)` → take `[-1]`.
- Fallback if no tags are present: strip leading lines until the first markdown heading (`#`) and use the remainder.
- Keep the markdown citations exactly as-is — do not rewrite the `[[label](url)]` markers.

Validate this on the 2-task dry run (§4): open the output and confirm `article` starts at the report's first heading, contains the `[[label](url)]` citations, and has no `<final_answer>` tags or "I now have sufficient information" preamble.

---

## 3. The runner (`run_deepnews.py`)

Implemented at the repo root (`run_deepnews.py`). It loads the queries, runs each through `get_deep_news`, extracts the report body, and writes DRB-shaped lines to `data/test_data/raw_data/<model-tag>.jsonl`.

### Usage
```bash
# how many tasks to run:
python run_deepnews.py --limit 2          # first 2 tasks (smoke test)
python run_deepnews.py --limit 10 --only-en   # first 10 English-only tasks
python run_deepnews.py --ids 1,5,42        # specific task ids
python run_deepnews.py                      # all 100

# DeepNews config (all optional, sensible defaults shown):
python run_deepnews.py \
  --model claude-sonnet-4-6 --engine v1.5 \
  --search-depth 2 --max-depth 6 --max-parallel-tool-calls 4 \
  --sources asknews,google,wiki,x \
  --max-tokens 32000 --workers 4 --retries 3
```
`ASKNEWS_API_KEY` is read from the env (falls back to the key in `main.py` if unset).

### Flags
| Flag | Purpose |
|---|---|
| `-n, --limit N` | Run the first N tasks (after any language filter). Omit → all 100. |
| `--ids 1,5,42` | Run exactly these task ids (overrides `--limit`/language filters). |
| `--only-en` / `--only-zh` | Restrict to one language (50 each). |
| `--model` | DeepNews model under test (the report being scored). |
| `--engine` | `v1` / `v1.5` / `v2.0`. |
| `--search-depth` / `--max-depth` | Research depth band. Higher = better RACE, more cost/time. |
| `--max-tokens` | Output cap. **Default 32000** — the SDK default of 9999 truncates deep reports (the streamed reasoning counts against it too). |
| `--workers` | Concurrent DeepNews calls. |
| `--model-tag` | Output filename stem. Default `deepnews-<engine>-<model>-d<max_depth>`. |
| `--force` | Re-run tasks already present in the output. |

### What it does for correctness
- **Resumable** — appends each line as it completes; on restart it skips ids already in the file. Failed tasks are *not* written, so just re-run the same command to retry them.
- **Report extraction** — accumulates only content chunks (the stream also yields source objects, which have no `.choices`), then takes the **last** `<final_answer>…</final_answer>` block, falling back to "first markdown heading onward". Citations are left exactly as DeepNews emits them.
- **Guards** — rejects an article shorter than `--min-chars` (500) or with no `http` citation, so truncated/empty runs fail loudly instead of silently tanking the score.
- **DeepNews defaults set deliberately** — `inline_citations="markdown_link"` + `append_references=True` (FACT-compatible citations), `asknews_watermark=False` (keeps the watermark out of the judged report), `max_tokens=32000`.
- **Bounded concurrency + retries** — `ThreadPoolExecutor(--workers)`, exponential backoff (`--retries`).
- On finish it prints the exact `TARGET_MODELS=("<tag>")` line to paste into `run_benchmark.sh`.

---

## 4. Execution plan

**Phase 0 — env.** Create a venv and install everything (runner SDK + benchmark deps):
```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt        # includes asknews-sdk

# Keys: copy the template and fill it in (.env is gitignored).
cp .env.example .env
#   ASKNEWS_API_KEY  — DeepNews generation (run_deepnews.py auto-loads .env)
#   LLM_BACKEND=openai, OPENAI_API_KEY — gpt-5.5 (RACE) + gpt-5.4-mini (FACT)
#   JINA_API_KEY     — FACT web scraping (required regardless of backend)

# run_benchmark.sh does NOT auto-load .env — export the eval keys into the shell first:
set -a; source .env; set +a
```
> Defaults `RACE_MODEL=gpt-5.5`, `FACT_MODEL=gpt-5.4-mini` kick in automatically. Don't override them to a non-default judge unless you only care about internal A/B — a different judge makes scores non-comparable to the leaderboard.

**Phase 1 — dry run (2 tasks, 1 EN + 1 ZH).** Generate two reports and inspect them:
```bash
python run_deepnews.py --ids 1,51        # id 1 is zh, id 51 is en
```
Open `data/test_data/raw_data/deepnews-v1.5-claude-sonnet-4-6-d6.jsonl` and confirm: (a) `article` starts at the report's first heading — no preamble, no `<final_answer>` tags, (b) it contains inline `[label](url)` citations, (c) the zh task returns a zh report. Then validate the eval end-to-end cheaply:
```bash
# TARGET_MODELS in run_benchmark.sh is already set to deepnews-v1.5-claude-sonnet-4-6-d6
# uncomment LIMIT="--limit 2" in run_benchmark.sh for the 2-task check
bash run_benchmark.sh
```
Confirm `results/race/<tag>/race_result.txt` and `results/fact/<tag>/fact_result.txt` populate.

**Phase 1.5 — optional cheaper first pass.** English-only (50 tasks) roughly halves both generation and evaluation cost and is a fast way to get a directional score:
```bash
python run_deepnews.py --only-en
# then run_benchmark.sh with ONLY_EN="--only_en" uncommented
```

**Phase 2 — full generation.** Run the runner over all 100. Expect this to be the long pole (each task is a multi-minute agentic run; ~4 in parallel). Resume on any interruption — just re-run the same command. Sanity-check: `wc -l` on the output = 100, no truncated articles.
```bash
python run_deepnews.py            # resumes; skips ids already done
```

**Phase 3 — full evaluation.** Re-comment `LIMIT` (and `ONLY_EN` if set), run `bash run_benchmark.sh`. RACE scores every report vs the reference (criteria are pre-shipped — no generation calls); FACT extracts → dedups → Jina-scrapes → validates every citation. See §5 for costs.

**Phase 4 — read results.** `race_result.txt` (4 sub-dimensions + overall) and `fact_result.txt` (Citation Accuracy, Effective Citations). Compare against leaderboard entries. To attribute wins/losses, slice by `topic` and `language` from `query.jsonl`.

---

## 5. Cost (OpenAI evaluator)

**Pricing (2026):** GPT-5.5 (RACE) **$5 / $30** per 1M in/out (batch $2.50/$15); GPT-5.4-mini (FACT) **$0.75 / $4.50**.

Two facts from the DRB code shape the cost: RACE criteria are **pre-shipped** (`data/criteria_data/criteria.jsonl`) so RACE = ~1 scoring call per task (target + reference scored together, occasionally chunked for long articles); FACT validation is **1 call per unique cited URL** (~25–40/task for citation-heavy DeepNews reports), which is the FACT call driver.

| Phase | Judge model | ~Per task | **Full 100 tasks** |
|---|---|---|---|
| RACE | gpt-5.5 | ~$0.35–0.50 | **~$35–55** |
| FACT | gpt-5.4-mini | ~$0.20–0.35 | **~$20–35** |
| **Total OpenAI** | | | **~$55–90** (≈ **$70** typical) |

- **`--only-en`** (50 tasks) ≈ halves it → ~$25–45. The Phase-1 dry run (2 tasks) is ~$1–2.
- **Reruns / `--force`** multiply linearly.
- Batch API for RACE would ~halve that phase, but DRB calls the judge synchronously (would require editing `utils/api.py`).

**Not OpenAI costs (don't forget):**
- **Jina** (FACT scraping) — required regardless of backend; free tier + cheap paid (a few $ for a full run).
- **AskNews / DeepNews generation** — the 100 deep-research runs themselves, billed by AskNews (not OpenAI), and likely your **largest single cost**. Scales with `--max-depth`, `--max-parallel-tool-calls`, and source count. Check your AskNews per-request/credit rate before the full run.

## 5b. Time / risk

| Item | Driver | Mitigation |
|---|---|---|
| **Generation time** | 100 multi-step agent runs, minutes each | `--workers 4`; resume on interruption |
| **Agent chatter / `<final_answer>` tags leak into article** | DeepNews streams reasoning + tagged report | `extract_report()` in the runner; verify in Phase 1 — **top risk for RACE** |
| **Truncated/short articles** | Stream drops, timeouts, `max_tokens` too low | `--max-tokens 32000`, length + `http` guard, resume; never emit partials |
| **Comparability** | Must use GPT-5.5 evaluator (current official) | Keep default `RACE_MODEL`/`FACT_MODEL`; don't swap judges |
| **gpt-5.5 access** | Your OpenAI key must be entitled to gpt-5.5 | Verify before the full run, or use OpenRouter as fallback backend |
| **Reproducibility (for leaderboard)** | Closed-source agent | Config encoded in `--model-tag`; document the exact `get_deep_news` flags |

## 6. Decisions to lock before running
- **Model under test** — `claude-sonnet-4-6` vs `claude-opus-4-6` vs `open-source-best`. Fix one; it defines "the DeepNews score." Optionally benchmark 2–3 as separate model tags.
- **Depth budget** — `search_depth` / `max_depth`. Higher = better RACE, more cost. Recommend pinning `max_depth=6` and noting it.
- **Source set** — `["asknews","google","wiki","x"]` is a reasonable default; add `reddit`/`graph` if the topic mix benefits.
- **Report extraction** — confirm `extract_report()` matches the real stream shape in Phase 1 (§2). Citations themselves need no work — DRB parses DeepNews' `[[label](url)]` format natively.

## 7. Leaderboard submission (optional)
Per DRB README, to get an official entry email the maintainers with: the raw `<model>.jsonl`, a temporary GPT-5.5 key for verification, a reproducibility/product link, model metadata, and (recommended) the `race_result.txt` / `fact_result.txt`.

---

### TL;DR
1. `python run_deepnews.py --ids 1,51` — dry run; eyeball the two reports.
2. `python run_deepnews.py` — generate all 100 (resumable; use `--limit`/`--only-en`/`--ids` to scope).
3. Set `TARGET_MODELS=("<tag>")`, export `LLM_BACKEND=openai` + `OPENAI_API_KEY` (gpt-5.5 access) + `JINA_API_KEY`, then `bash run_benchmark.sh`.
4. Read RACE + FACT; slice by topic/language. Budget **~$70 of OpenAI** for a full eval (plus Jina + AskNews generation). Citations are already DRB-compatible — the make-or-break detail is **cleanly extracting the report body** from the agent stream, which the runner handles.
