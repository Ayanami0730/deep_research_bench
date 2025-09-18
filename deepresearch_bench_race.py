import argparse
import concurrent.futures
import json
import logging
import os
import threading
import time
from typing import Union, Optional, List, Dict, Tuple

from tqdm import tqdm

# Import scoring prompts for Chinese and English
from prompt.score_prompt_en import generate_merged_score_prompt as en_merged_score_prompt
from prompt.score_prompt_zh import generate_merged_score_prompt as zh_merged_score_prompt
from utils.api import AIClient
from utils.clean_article import ArticleCleaner
from utils.io_utils import load_jsonl
from utils.json_extractor import extract_json_from_markdown
from utils.score_calculator import calculate_weighted_scores

# Configure logging - 将级别从INFO改为WARNING
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# 关键信息仍然需要输出，设置当前模块的日志级别为INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fixed configuration parameters
CRITERIA_FILE = "data/criteria_data/criteria.jsonl"
REFERENCE_FILE = "data/test_data/cleaned_data/reference.jsonl"
MAX_RETRIES = 10


def update_progress(pbar: tqdm, lock: threading.Lock):
    with lock:
        pbar.update(1)


def validate_task_data(task_id: str, prompt: str,
                       target_articles_map: Dict[str, dict],
                       reference_articles_map: Dict[str, dict],
                       criteria_map: Dict[str, dict]) -> Tuple[str, str, dict]:
    """Ensure all required data exists for this task."""
    if prompt not in target_articles_map:
        raise ValueError(f"ID {task_id}: Target article not found")
    if prompt not in reference_articles_map:
        raise ValueError(f"ID {task_id}: Reference article not found")
    if prompt not in criteria_map:
        raise ValueError(f"ID {task_id}: Evaluation criteria not found")

    target_article = target_articles_map[prompt].get("article", "")
    reference_article = reference_articles_map[prompt].get("article", "")
    criteria_data = criteria_map[prompt]
    return target_article, reference_article, criteria_data


def build_user_prompt(language: str, prompt: str, target_article: str,
                      reference_article: str, criteria_list_str: str) -> str:
    """Assemble the LLM scoring prompt."""
    merged_score_prompt = zh_merged_score_prompt if language == "zh" else en_merged_score_prompt
    return merged_score_prompt.format(
        task_prompt=prompt,
        article_1=target_article,
        article_2=reference_article,
        criteria_list=criteria_list_str
    )


def call_llm_with_retries(user_prompt: str, llm_client: AIClient,
                          max_retries: int, task_id: str) -> Optional[dict]:
    """Call LLM, retry on transient errors, and return parsed JSON."""
    retry_count = 0
    while retry_count < max_retries:
        try:
            llm_response_str = llm_client.generate(user_prompt=user_prompt, system_prompt="")
            json_str_extracted = extract_json_from_markdown(llm_response_str)
            if not json_str_extracted:
                raise ValueError("Failed to extract JSON from LLM response")
            llm_output_json = json.loads(json_str_extracted)

            # Ensure required dimensions exist
            expected_dims = ["comprehensiveness", "insight", "instruction_following", "readability"]
            missing_dims = [dim for dim in expected_dims if dim not in llm_output_json]
            if missing_dims:
                raise ValueError(f"Missing expected dimensions: {missing_dims}")

            return llm_output_json

        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                logger.warning(f"ID {task_id}: Retry {retry_count}/{max_retries} - {str(e)}")
                time.sleep(1.5 ** retry_count)
            else:
                logger.error(f"ID {task_id}: Failed after {max_retries} retries - {str(e)}")
                return None


def calculate_normalized_scores(scores: dict, criteria_data: dict, task_id: str) -> Dict[str, float]:
    """Normalize per-dimension and overall scores."""
    target_total = scores["target"]["total"]
    reference_total = scores["reference"]["total"]
    overall_score = target_total / (target_total + reference_total) if target_total + reference_total > 0 else 0

    normalized_dims = {}
    for dim in ["comprehensiveness", "insight", "instruction_following", "readability"]:
        dim_key = f"{dim}_weighted_avg"
        if dim_key in scores["target"]["dims"]:
            target_score = scores["target"]["dims"][dim_key]
            reference_score = scores["reference"]["dims"][dim_key]
            if target_score + reference_score > 0:
                normalized_dims[dim] = target_score / (target_score + reference_score)
            else:
                normalized_dims[dim] = 0
        else:
            logger.warning(f"ID {task_id}: Missing dimension {dim_key} in scores")
            normalized_dims[dim] = 0

    return {**normalized_dims, "overall_score": overall_score}


def process_single_item(task_data: dict, target_articles_map: dict, reference_articles_map: dict,
                        criteria_map: dict, llm_client: AIClient, lock: threading.Lock,
                        pbar: tqdm, max_retries: int, language: str) -> dict:
    """Process a single scoring task and return result or error info."""
    task_id, prompt = task_data.get("id"), task_data.get("prompt")

    try:
        target_article, reference_article, criteria_data = validate_task_data(
            task_id, prompt, target_articles_map, reference_articles_map, criteria_map
        )
        criteria_list_str = json.dumps(
            {dim: [{"criterion": c["criterion"], "explanation": c["explanation"]}
                   for c in criterions if isinstance(c, dict) and "criterion" in c and "explanation" in c]
             for dim, criterions in criteria_data.get("criterions", {}).items() if isinstance(criterions, list)},
            ensure_ascii=False, indent=2
        )
    except Exception as e:
        update_progress(pbar, lock)
        return {"id": task_id, "prompt": prompt, "error": str(e)}

    user_prompt = build_user_prompt(language, prompt, target_article, reference_article, criteria_list_str)
    llm_output_json = call_llm_with_retries(user_prompt, llm_client, max_retries, task_id)

    if not llm_output_json:
        update_progress(pbar, lock)
        return {"id": task_id, "prompt": prompt, "error": f"Failed after {max_retries} retries"}

    try:
        scores = calculate_weighted_scores(llm_output_json, criteria_data, language)
        normalized = calculate_normalized_scores(scores, criteria_data, task_id)
    except Exception as e:
        update_progress(pbar, lock)
        return {"id": task_id, "prompt": prompt, "error": f"Error calculating scores: {str(e)}"}

    update_progress(pbar, lock)
    return {"id": task_id, "prompt": prompt, **normalized}


def process_language_data(language: str, target_model: str, llm_client: AIClient, clean_agent: AIClient,
                          raw_data_dir: str, skip_cleaning: bool, cleaned_data_dir: str, max_workers: int,
                          limit: Optional[int], query_file: str) -> Optional[List[dict]]:
    """Process data for a single language (Chinese or English)."""

    # Step 1: Clean articles
    if skip_cleaning:
        lang_name = "Chinese" if language == "zh" else "English"
        logger.info(f"Skipping article cleaning step for {lang_name} data.")
        target_data_dir = raw_data_dir
    else:
        logger.info(f"Checking if {target_model} articles need cleaning...")
        try:
            article_cleaner  = ArticleCleaner(clean_agent)
            article_cleaner.clean_articles(
                target_model, raw_data_dir, cleaned_data_dir,
                max_workers, MAX_RETRIES, limit, language
            )
            target_data_dir = cleaned_data_dir
        except Exception as e:
            logger.error(f"Article cleaning failed for {target_model}: {e}")
            return None

    # Step 2: Load data
    try:
        all_tasks = [t for t in load_jsonl(query_file) if t.get("language") == language]
        if limit: all_tasks = all_tasks[:limit]

        task_prompts = {t["prompt"] for t in all_tasks if "prompt" in t}
        criteria_list = [c for c in load_jsonl(CRITERIA_FILE) if c.get("prompt") in task_prompts]
        target_articles_list = [a for a in load_jsonl(os.path.join(target_data_dir, f"{target_model}.jsonl"))
                                if a.get("prompt") in task_prompts]
        reference_articles_list = [a for a in load_jsonl(REFERENCE_FILE) if a.get("prompt") in task_prompts]

        if not target_articles_list:
            logger.error(f"No target articles found for model {target_model} in {language}")
            return None

        criteria_map = {c["prompt"]: c for c in criteria_list}
        target_articles_map = {a["prompt"]: a for a in target_articles_list}
        reference_articles_map = {a["prompt"]: a for a in reference_articles_list}

        tasks_to_process = [
            t for t in all_tasks
            if t.get("prompt") in criteria_map
               and t.get("prompt") in target_articles_map
               and t.get("prompt") in reference_articles_map
        ]
        if not tasks_to_process:
            logger.error(f"No complete task data found for {language}")
            return None

        logger.info(f"Processing {len(tasks_to_process)} {language} tasks...")

    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")
        return None

    # Step 3: Score tasks concurrently
    results_list = []
    lock = threading.Lock()

    with tqdm(total=len(tasks_to_process), desc=f"Scoring {language} {target_model}") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_single_item,
                    task, target_articles_map, reference_articles_map,
                    criteria_map, llm_client, lock, pbar, MAX_RETRIES, language
                )
                for task in tasks_to_process
            ]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    results_list.append(result)

    successful = [r for r in results_list if "error" not in r]
    logger.info(f"{language} evaluation complete. Scored {len(successful)} / {len(tasks_to_process)} successfully.")
    return successful


def load_existing_results(output_dir: str, force: bool, limit: int, target_model: str) -> tuple:
    """Load existing results from disk unless force is set."""
    output_file = os.path.join(output_dir, f"{target_model}/raw_results.jsonl")
    existing_results, existing_ids = [], set()

    if os.path.exists(output_file) and not force:
        try:
            existing_results = load_jsonl(output_file)
            existing_ids = {r.get('id') for r in existing_results if r.get('id')}
            logger.info(f"Found existing results file with {len(existing_results)} entries")

            if limit is not None and len(existing_results) >= limit:
                logger.info(
                    f"Existing results ({len(existing_results)}) meet or exceed limit ({limit}). Skipping evaluation."
                )
                summarize_results(existing_results)
                return existing_results, existing_ids
        except Exception as e:
            logger.warning(f"Error reading existing results file: {e}. Will create new results.")

    return existing_results, existing_ids


def summarize_results(results: List[Dict]) -> Union[dict, None]:
    """Compute averages and log a summary of results."""
    successful = [r for r in results if "error" not in r]
    if not successful:
        return None

    summary = {
        "comprehensiveness": sum(r.get("comprehensiveness", 0) for r in successful) / len(successful),
        "insight": sum(r.get("insight", 0) for r in successful) / len(successful),
        "instruction_following": sum(r.get("instruction_following", 0) for r in successful) / len(successful),
        "readability": sum(r.get("readability", 0) for r in successful) / len(successful),
        "overall": sum(r.get("overall_score", 0) for r in successful) / len(successful),
    }

    logger.info("\n=== Evaluation Results Summary ===")
    logger.info(f"Comprehensiveness:      {summary['comprehensiveness']:.4f}")
    logger.info(f"Insight:                {summary['insight']:.4f}")
    logger.info(f"Instruction Following:  {summary['instruction_following']:.4f}")
    logger.info(f"Readability:            {summary['readability']:.4f}")
    logger.info(f"Overall Score:          {summary['overall']:.4f}")
    logger.info("================================")

    return summary


def save_results(results, output_dir: str, target_model: str):
    """Save results and summary to disk."""
    os.makedirs(os.path.join(output_dir, f"{target_model}"), exist_ok=True)
    output_file = os.path.join(output_dir, f"{target_model}/raw_results.jsonl")
    result_file = os.path.join(output_dir, f"{target_model}/race_result.txt")

    results.sort(key=lambda x: x.get('id', float('inf')))
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
        logger.info(f"Results saved successfully to {output_file}")

        summary = summarize_results(results)
        if summary:
            with open(result_file, 'w', encoding='utf-8') as f:
                for k, v in summary.items():
                    f.write(f"{k.capitalize()}: {v:.4f}\n")
            logger.info(f"Summary written to {result_file}")

    except IOError as e:
        logger.error(f"Failed to write results: {e}")


def get_tasks_to_process(lang: str, args: argparse.Namespace, all_tasks: List[Dict], existing_results: List[Dict],
                         existing_ids: dict) -> list:
    """Filter and limit tasks for a given language."""
    lang_name = "Chinese" if lang == "zh" else "English"
    logger.info(f"Starting {lang_name} data processing...")

    tasks = [
        task for task in all_tasks
        if task.get("language") == lang and task.get("id") not in existing_ids
    ]
    if not tasks:
        logger.info(f"All {lang_name} tasks have been processed already. Skipping.")
        return []

    if args.limit is not None:
        existing_count = len([
            r for r in existing_results
            if r.get("prompt", "").strip() and
               any(t.get("prompt") == r.get("prompt") and t.get("language") == lang for t in all_tasks)
        ])
        remaining_limit = max(0, args.limit - existing_count)

        if remaining_limit <= 0:
            logger.info(f"Already reached limit for {lang_name} tasks ({existing_count}/{args.limit}). Skipping.")
            return []

        logger.info(
            f"Processing up to {remaining_limit} more {lang_name} tasks "
            f"(limit: {args.limit}, already processed: {existing_count})"
        )
        return tasks[:remaining_limit]

    return tasks


def main():
    # keep argparse inline as requested
    parser = argparse.ArgumentParser(
        description='Score model articles against reference articles using detailed evaluation criteria and LLM.')
    parser.add_argument('target_model', type=str, help='Name of target model to evaluate')
    parser.add_argument('--limit', type=int, default=None, help='Limit on number of prompts to process (for testing).')
    parser.add_argument('--skip_cleaning', action='store_true', help='Skip article cleaning step.')
    parser.add_argument('--only_zh', action='store_true', help='Only process Chinese data.')
    parser.add_argument('--only_en', action='store_true', help='Only process English data.')
    parser.add_argument('--force', action='store_true', help='Force re-evaluation even if results exist.')
    parser.add_argument('--raw_data_dir', type=str, default="data/test_data/raw_data",
                        help='Directory containing raw data.')
    parser.add_argument('--cleaned_data_dir', type=str, default="data/test_data/cleaned_data",
                        help='Directory for cleaned data.')
    parser.add_argument('--max_workers', type=int, default=5, help='Maximum number of worker threads.')
    parser.add_argument('--query_file', type=str, default="data/prompt_data/query.jsonl",
                        help='Path to query file with language information.')
    parser.add_argument('--output_dir', type=str, default="results", help='Directory for output results.')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load existing results if available
    existing_results, existing_ids = load_existing_results(args.output_dir, args.force, args.limit, args.target_model)

    llm_client = AIClient()
    clean_agent = llm_client
    all_results = list(existing_results)

    all_tasks = load_jsonl(args.query_file)
    if existing_ids:
        logger.info(f"Will skip {len(existing_ids)} already processed task IDs")

    # Process each language
    for lang in ["zh", "en"]:

        if (lang == "zh" and args.only_en) or (lang == "en" and args.only_zh):
            continue

        tasks = get_tasks_to_process(lang, args, all_tasks, existing_results, existing_ids)
        if not tasks:
            continue

        results = process_language_data(
            lang, args.target_model, llm_client, clean_agent,
            args.raw_data_dir, args.skip_cleaning, args.cleaned_data_dir,
            args.max_workers, len(tasks), args.query_file
        )
        if results:
            all_results.extend(results)

    # Save results if available
    if all_results:
        save_results(all_results, args.output_dir, args.target_model)
    else:
        logger.warning("No results to save.")

    logger.info("--- Run Summary ---")
    logger.info(f"Target model: {args.target_model}")
    logger.info(f"Total tasks processed: {len(all_results)}")
    logger.info(f"Results dir: {args.output_dir}")
    logger.info("-------------------")


if __name__ == "__main__":
    main()
