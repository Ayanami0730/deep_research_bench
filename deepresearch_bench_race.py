import json
import os
import threading
import concurrent.futures
import argparse
from tqdm import tqdm
import logging
import time
import re 
from utils.api import AIClient, CLEAN_Model
from utils.io_utils import load_jsonl
import glob

# Import scoring prompts for Chinese and English
from prompt.score_prompt_zh import generate_merged_score_prompt as zh_merged_score_prompt
from prompt.score_prompt_en import generate_merged_score_prompt as en_merged_score_prompt
from utils.score_calculator import calculate_weighted_scores
from utils.json_extractor import extract_json_from_markdown
from utils.clean_article import ArticleCleaner

# Configure logging - 将级别从INFO改为WARNING
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# 关键信息仍然需要输出，设置当前模块的日志级别为INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fixed configuration parameters
CRITERIA_FILE = "data/criteria_data/criteria.jsonl"
REFERENCE_FILE = "data/test_data/cleaned_data/reference.jsonl"
MAX_RETRIES = 10

def format_criteria_list(criteria_data):
    """Format evaluation criteria list as JSON string, without weight information"""
    criteria_for_prompt = {}
    criterions_dict = criteria_data.get("criterions", {})

    for dim, criterions_list in criterions_dict.items():
        if not isinstance(criterions_list, list):
            logger.warning(f"Value for dimension '{dim}' is not a list. Skipping.")
            continue

        criteria_for_prompt[dim] = []
        for crit_item in criterions_list:
            if isinstance(crit_item, dict) and "criterion" in crit_item and "explanation" in crit_item:
                criteria_for_prompt[dim].append({
                    "criterion": crit_item["criterion"],
                    "explanation": crit_item["explanation"]
                })
            else:
                logger.warning(f"Invalid criteria format in dimension '{dim}'. Skipping item.")

    try:
        return json.dumps(criteria_for_prompt, ensure_ascii=False, indent=2)
    except TypeError as e:
        raise ValueError(f"Failed to serialize criteria to JSON: {e}")

def process_single_item(task_data, target_articles_map, reference_articles_map, criteria_map, 
                         llm_client, lock, pbar, max_retries, language):
    """Process a single task: get data, call LLM, parse results, calculate scores"""
    task_id = task_data.get('id')
    prompt = task_data.get('prompt')

    # Data retrieval and validation
    if prompt not in target_articles_map:
        logger.error(f"Target article not found for ID {task_id}")
        with lock: pbar.update(1)
        return {"id": task_id, "prompt": prompt, "error": "Target article not found"}
    
    if prompt not in reference_articles_map:
        logger.error(f"Reference article not found for ID {task_id}")
        with lock: pbar.update(1)
        return {"id": task_id, "prompt": prompt, "error": "Reference article not found"}
    
    if prompt not in criteria_map:
        logger.error(f"Evaluation criteria not found for ID {task_id}")
        with lock: pbar.update(1)
        return {"id": task_id, "prompt": prompt, "error": "Evaluation criteria not found"}

    target_article_data = target_articles_map[prompt]
    reference_article_data = reference_articles_map[prompt]
    criteria_data = criteria_map[prompt]

    target_article = target_article_data.get('article', '')
    reference_article = reference_article_data.get('article', '')

    # Format evaluation criteria list in JSON
    try:
        criteria_list_str = format_criteria_list(criteria_data)
    except ValueError as e:
        logger.error(f"ID {task_id}: {str(e)}")
        with lock: pbar.update(1)
        return {"id": task_id, "prompt": prompt, "error": f"Failed to format criteria: {str(e)}"}

    # Choose scoring prompt based on language
    merged_score_prompt = zh_merged_score_prompt if language == "zh" else en_merged_score_prompt
    
    # Prepare LLM prompt
    user_prompt = merged_score_prompt.format(
        task_prompt=prompt,
        article_1=target_article,
        article_2=reference_article,
        criteria_list=criteria_list_str 
    )

    llm_response_str = None
    llm_output_json = None
    success = False
    retry_count = 0

    while retry_count < max_retries and not success:
        try:
            llm_response_str = llm_client.generate(
                user_prompt=user_prompt,
                system_prompt=""
            )

            # Extract JSON from response
            json_str_extracted = extract_json_from_markdown(llm_response_str)
            if not json_str_extracted:
                raise ValueError("Failed to extract JSON from LLM response")
                
            llm_output_json = json.loads(json_str_extracted)
            
            # Check if all required dimensions exist
            expected_dims = ["comprehensiveness", "insight", "instruction_following", "readability"]
            if not all(dim in llm_output_json for dim in expected_dims):
                missing_dims = [dim for dim in expected_dims if dim not in llm_output_json]
                raise ValueError(f"Missing expected dimensions: {missing_dims}")
            
            # All checks passed
            success = True
            
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                logger.warning(f"ID {task_id}: Retry {retry_count}/{max_retries} - {str(e)}")
                time.sleep(1.5 ** retry_count)
            else:
                logger.error(f"ID {task_id}: Failed after {max_retries} retries - {str(e)}")
    
    if not success:
        with lock: pbar.update(1)
        return {
            "id": task_id,
            "prompt": prompt,
            "error": f"Failed to get valid response after {max_retries} retries",
            "model_output": llm_response_str[:500] if llm_response_str else "No response"
        }

    # Calculate weighted scores
    try:
        scores = calculate_weighted_scores(llm_output_json, criteria_data, language)
        
        # Calculate overall score = target / (target + reference)
        target_total = scores["target"]["total"]
        reference_total = scores["reference"]["total"]
        overall_score = 0
        if target_total + reference_total > 0:
            overall_score = target_total / (target_total + reference_total)
        
        # Calculate normalized dimension scores
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
        
    except Exception as e:
        logger.error(f"ID {task_id}: Error calculating scores - {str(e)}")
        with lock: pbar.update(1)
        return {
            "id": task_id,
            "prompt": prompt,
            "error": f"Error calculating scores: {str(e)}"
        }

    # Prepare final result with simplified format
    final_result = {
        "id": task_id,
        "prompt": prompt,
        "comprehensiveness": normalized_dims.get("comprehensiveness", 0),
        "insight": normalized_dims.get("insight", 0),
        "instruction_following": normalized_dims.get("instruction_following", 0),
        "readability": normalized_dims.get("readability", 0),
        "overall_score": overall_score
    }

    with lock:
        pbar.update(1)

    return final_result

def process_language_data(language, target_model, llm_client, clean_agent, 
                         raw_data_dir, cleaned_data_dir, max_workers, limit, query_file):
    """Process data for a single language (Chinese or English)"""
    
    # Step 1: Clean target model articles if needed
    logger.info(f"Checking if {target_model} articles need cleaning...")
    try:
        article_cleaner = ArticleCleaner(clean_agent)
        default_language = language

        article_cleaner.clean_articles(
            target_model, 
            raw_data_dir, 
            cleaned_data_dir, 
            max_workers,
            MAX_RETRIES,
            limit,
            default_language
            )
        cleaning_success = True
    except Exception as e:
        logger.error(f"Article cleaning failed for {target_model}: {e}")
        cleaning_success = False

    
    if not cleaning_success:
        logger.error(f"Article cleaning failed for {target_model}, cannot continue.")
        return None
    
    # Step 2: Load data for scoring
    logger.info(f"Loading {language} data from {query_file}...")
    
    try:
        all_tasks = load_jsonl(query_file)
        all_tasks = [task for task in all_tasks if task.get('language') == language]
            
        # Apply limit if specified
        if limit is not None and limit > 0:
            all_tasks = all_tasks[:limit]
            
        # Get prompts from tasks
        task_prompts = {task['prompt'] for task in all_tasks if 'prompt' in task}
        
        # Load criteria data
        all_criteria = load_jsonl(CRITERIA_FILE)
        criteria_list = [c for c in all_criteria if c.get('prompt') in task_prompts]
            
        # Load target model articles
        target_file = os.path.join(cleaned_data_dir, f"{target_model}.jsonl")
        all_target_articles = load_jsonl(target_file)
        target_articles_list = [a for a in all_target_articles if a.get('prompt') in task_prompts]
        if not target_articles_list:
            logger.error(f"No target articles found for model {target_model} in {language}")
            return None
            
        # Load reference articles
        all_reference_articles = load_jsonl(REFERENCE_FILE)
        reference_articles_list = [a for a in all_reference_articles if a.get('prompt') in task_prompts]
            
        # Build mappings
        criteria_map = {item['prompt']: item for item in criteria_list}
        target_articles_map = {item['prompt']: item for item in target_articles_list}
        reference_articles_map = {item['prompt']: item for item in reference_articles_list}
        
        # Check for missing data
        for task in all_tasks:
            prompt = task.get('prompt')
            if prompt not in criteria_map:
                logger.warning(f"No criteria found for task prompt: {prompt[:50]}...")
            if prompt not in target_articles_map:
                logger.warning(f"No target article found for task prompt: {prompt[:50]}...")
            if prompt not in reference_articles_map:
                logger.warning(f"No reference article found for task prompt: {prompt[:50]}...")
                
        # Filter out tasks with missing data
        tasks_to_process = [task for task in all_tasks 
                           if task.get('prompt') in criteria_map
                           and task.get('prompt') in target_articles_map
                           and task.get('prompt') in reference_articles_map]
        
        if not tasks_to_process:
            logger.error(f"No complete task data found for {language}")
            return None
            
        logger.info(f"Processing {len(tasks_to_process)} {language} tasks...")
        
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")
        return None
    
    # Step 3: Process each task and generate scores
    lock = threading.Lock()
    results_list = []
    
    with tqdm(total=len(tasks_to_process), desc=f"Scoring {language} {target_model}") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_single_item,
                    task,
                    target_articles_map,
                    reference_articles_map,
                    criteria_map,
                    llm_client,
                    lock,
                    pbar,
                    MAX_RETRIES,
                    language
                )
                for task in tasks_to_process
            ]
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    results_list.append(result)
    
    successful_results = [res for res in results_list if "error" not in res]
    
    logger.info(f"{language} evaluation complete. Successfully scored {len(successful_results)} "
                 f"out of {len(tasks_to_process)} tasks.")
    
    return successful_results

def main():
    parser = argparse.ArgumentParser(description='Score model articles against reference articles using detailed evaluation criteria and LLM.')
    parser.add_argument('target_model', type=str, help='Name of target model to evaluate')
    parser.add_argument('--limit', type=int, default=None, help='Limit on number of prompts to process (for testing).')
    parser.add_argument('--skip_cleaning', action='store_true', help='Skip article cleaning step.')
    parser.add_argument('--only_zh', action='store_true', help='Only process Chinese data.')
    parser.add_argument('--only_en', action='store_true', help='Only process English data.')
    parser.add_argument('--force', action='store_true', help='Force re-evaluation even if results exist.')
    
    # Add only the parameters that need to be configurable via command line
    parser.add_argument('--raw_data_dir', type=str, default="data/test_data/raw_data", help='Directory containing raw data.')
    parser.add_argument('--cleaned_data_dir', type=str, default="data/test_data/cleaned_data", help='Directory for cleaned data.')
    parser.add_argument('--max_workers', type=int, default=5, help='Maximum number of worker threads.')
    parser.add_argument('--query_file', type=str, default="data/prompt_data/query.jsonl", help='Path to query file with language information.')
    parser.add_argument('--output_dir', type=str, default="results", help='Directory for output results.')

    args = parser.parse_args()

    # Extract parameters from args
    target_model = args.target_model
    limit = args.limit
    skip_cleaning = args.skip_cleaning
    only_zh = args.only_zh
    only_en = args.only_en
    force = args.force
    raw_data_dir = args.raw_data_dir
    cleaned_data_dir = args.cleaned_data_dir
    max_workers = args.max_workers
    query_file = args.query_file
    output_dir = args.output_dir
    
    os.makedirs(output_dir, exist_ok=True)
    
    # check if the results file exists
    output_file = os.path.join(output_dir, "raw_results.jsonl")
    result_file = os.path.join(output_dir, "race_result.txt")
    existing_results = []
    existing_ids = set()
    
    if os.path.exists(output_file) and not force:
        try:
            existing_results = load_jsonl(output_file)
            existing_ids = {r.get('id') for r in existing_results if r.get('id')}
            logger.info(f"Found existing results file with {len(existing_results)} entries")
            
            # if limit is specified and the number of existing results is greater than or equal to limit, return
            if limit is not None and len(existing_results) >= limit:
                logger.info(f"Existing results ({len(existing_results)}) meet or exceed limit ({limit}). Skipping evaluation.")
                
                # calculate and print the average scores of the existing results
                successful_results = [r for r in existing_results if "error" not in r]
                if successful_results:
                    comprehensiveness_avg = sum(r.get("comprehensiveness", 0) for r in successful_results) / len(successful_results)
                    insight_avg = sum(r.get("insight", 0) for r in successful_results) / len(successful_results)
                    instruction_following_avg = sum(r.get("instruction_following", 0) for r in successful_results) / len(successful_results)
                    readability_avg = sum(r.get("readability", 0) for r in successful_results) / len(successful_results)
                    overall_avg = sum(r.get("overall_score", 0) for r in successful_results) / len(successful_results)
                    
                    logger.info("\n=== Existing Evaluation Results Summary ===")
                    logger.info(f"Comprehensiveness:      {comprehensiveness_avg:.4f}")
                    logger.info(f"Insight:                {insight_avg:.4f}")
                    logger.info(f"Instruction Following:  {instruction_following_avg:.4f}")
                    logger.info(f"Readability:            {readability_avg:.4f}")
                    logger.info(f"Overall Score:          {overall_avg:.4f}")
                    logger.info("================================")
                
                return
        except Exception as e:
            logger.warning(f"Error reading existing results file: {e}. Will create new results.")
            existing_results = []
            existing_ids = set()
    
    llm_client = AIClient()
    clean_agent = AIClient(model=CLEAN_Model)
    
    all_results = list(existing_results)  # initialize with existing results
    
    # load all tasks, filter out the processed task IDs
    all_tasks = load_jsonl(query_file)
    if existing_ids:
        logger.info(f"Will skip {len(existing_ids)} already processed task IDs")
    
    # chinese data processing
    if not only_en:
        logger.info("Starting Chinese data processing...")
        if not skip_cleaning:
            # filter out the processed chinese tasks
            zh_tasks = [task for task in all_tasks if task.get('language') == 'zh' and task.get('id') not in existing_ids]
            if not zh_tasks:
                logger.info("All Chinese tasks have been processed already. Skipping.")
            elif limit is not None:
                # if limit is specified, consider the number of existing results and new tasks
                existing_zh_count = len([r for r in existing_results if r.get('prompt', '').strip() and 
                                       any(t.get('prompt') == r.get('prompt') and t.get('language') == 'zh' 
                                           for t in all_tasks)])
                remaining_limit = max(0, limit - existing_zh_count)
                if remaining_limit > 0:
                    logger.info(f"Processing up to {remaining_limit} more Chinese tasks (limit: {limit}, already processed: {existing_zh_count})")
                    zh_results = process_language_data(
                        "zh", target_model, llm_client, clean_agent,
                        raw_data_dir, cleaned_data_dir, max_workers, remaining_limit, query_file
                    )
                    if zh_results:
                        all_results.extend(zh_results)
                else:
                    logger.info(f"Already reached limit for Chinese tasks ({existing_zh_count}/{limit}). Skipping.")
            else:
                # if limit is not specified, process all unprocessed tasks
                zh_results = process_language_data( 
                    "zh", target_model, llm_client, clean_agent,
                    raw_data_dir, cleaned_data_dir, max_workers, limit, query_file
                )
                if zh_results:
                    all_results.extend(zh_results)
        else:
            logger.info("Skipping article cleaning step for Chinese data.")

    # english data processing
    if not only_zh:
        logger.info("Starting English data processing...")
        if not skip_cleaning:
            # filter out the processed english tasks
            en_tasks = [task for task in all_tasks if task.get('language') == 'en' and task.get('id') not in existing_ids]
            if not en_tasks:
                logger.info("All English tasks have been processed already. Skipping.")
            elif limit is not None:
                # if limit is specified, consider the number of existing results and new tasks
                existing_en_count = len([r for r in existing_results if r.get('prompt', '').strip() and 
                                       any(t.get('prompt') == r.get('prompt') and t.get('language') == 'en' 
                                           for t in all_tasks)])
                remaining_limit = max(0, limit - existing_en_count)
                if remaining_limit > 0:
                    logger.info(f"Processing up to {remaining_limit} more English tasks (limit: {limit}, already processed: {existing_en_count})")
                    en_results = process_language_data(
                        "en", target_model, llm_client, clean_agent,
                        raw_data_dir, cleaned_data_dir, max_workers, remaining_limit, query_file
                    )
                    if en_results:
                        all_results.extend(en_results)
                else:
                    logger.info(f"Already reached limit for English tasks ({existing_en_count}/{limit}). Skipping.")
            else:
                # if limit is not specified, process all unprocessed tasks
                en_results = process_language_data(
                    "en", target_model, llm_client, clean_agent,
                    raw_data_dir, cleaned_data_dir, max_workers, limit, query_file
                )
                if en_results:
                    all_results.extend(en_results)
        else:
            logger.info("Skipping article cleaning step for English data.")
    
    # output results to file
    if all_results:
        # sort by ID
        all_results.sort(key=lambda x: x.get('id', float('inf')))
        
        logger.info(f"Saving {len(all_results)} results to {output_file}...")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for result in all_results:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
            logger.info("Results saved successfully.")
            
            # calculate and print the average scores
            successful_results = [r for r in all_results if "error" not in r]
            if successful_results:

                comprehensiveness_avg = sum(r.get("comprehensiveness", 0) for r in successful_results) / len(successful_results)
                insight_avg = sum(r.get("insight", 0) for r in successful_results) / len(successful_results)
                instruction_following_avg = sum(r.get("instruction_following", 0) for r in successful_results) / len(successful_results)
                readability_avg = sum(r.get("readability", 0) for r in successful_results) / len(successful_results)
                overall_avg = sum(r.get("overall_score", 0) for r in successful_results) / len(successful_results)
                
                logger.info("\n=== Evaluation Results Summary ===")
                logger.info(f"Comprehensiveness:      {comprehensiveness_avg:.4f}")
                logger.info(f"Insight:                {insight_avg:.4f}")
                logger.info(f"Instruction Following:  {instruction_following_avg:.4f}")
                logger.info(f"Readability:            {readability_avg:.4f}")
                logger.info(f"Overall Score:          {overall_avg:.4f}")
                logger.info("================================")

                # write the results to the result file
                with open(result_file, 'w', encoding='utf-8') as f:
                    f.write(f"Comprehensiveness: {comprehensiveness_avg:.4f}\n")
                    f.write(f"Insight: {insight_avg:.4f}\n")
                    f.write(f"Instruction Following: {instruction_following_avg:.4f}\n")
                    f.write(f"Readability: {readability_avg:.4f}\n")
                    f.write(f"Overall Score: {overall_avg:.4f}\n")

        except IOError as e:
            logger.error(f"Failed to write results to {output_file}: {e}")
    else:
        logger.warning("No results to save.")
    
    logger.info("--- Run Summary ---")
    logger.info(f"Target model: {target_model}")
    logger.info(f"Total tasks processed: {len(all_results)}")
    logger.info(f"Results file: {output_file}")
    logger.info("-------------------")

if __name__ == "__main__":
    main()
