import os
import argparse
import logging

from utils.extract import extract_all
from utils.deduplicate import deduplicate_all
from utils.scrape import scrape_all
from utils.validate import validate_all
from utils.stat import stat_all

# Configure logging - 将级别从INFO改为WARNING
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# 关键信息仍然需要输出，设置当前模块的日志级别为INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def run_fact_benchmark(
        target_model: str,
        limit: int,
        raw_data_dir: str,
        query_file: str,
        output_dir: str,
        n_total_process: int
) -> None:
    logger.info(f"========== Starting FACT evaluation for {target_model} ==========")

    # Create citation output directory
    if not output_dir:
        output_dir = os.path.join("results", "fact", target_model)
    os.makedirs(output_dir, exist_ok=True)

    raw_data_path = os.path.join(raw_data_dir, f"{target_model}.jsonl")

    # Phase 1: Extract citations
    logger.info(f"Extracting citations for {target_model}")
    extracted_path = os.path.join(output_dir, "extracted.jsonl")
    extract_all(
        output_path=extracted_path,
        raw_data_path=raw_data_path,
        query_data_path=query_file,
        n_total_process=n_total_process,
        limit=limit,
    )

    # Phase 2: Deduplicate citations
    logger.info(f"Deduplicating citations for {target_model}")
    deduplicated_path = os.path.join(output_dir, "deduplicated.jsonl")
    deduplicate_all(
        output_path=deduplicated_path,
        raw_data_path=extracted_path,
        query_data_path=query_file,
        n_total_process=n_total_process,
    )

    # Phase 3: Scrape webpages
    logger.info(f"Scraping webpages for {target_model}")
    scraped_path = os.path.join(output_dir, "scraped.jsonl")
    scrape_all(
        output_path=scraped_path,
        raw_data_path=deduplicated_path,
        n_total_process=n_total_process,
    )

    # Phase 4: Validate citations
    logger.info(f"Validating citations for {target_model}")
    validated_path = os.path.join(output_dir, "validated.jsonl")
    validate_all(
        output_path=validated_path,
        raw_data_path=scraped_path,
        query_data_path=query_file,
        n_total_process=n_total_process,
    )

    # Phase 5: Collect statistics
    logger.info(f"Collecting statistics for {target_model}")
    stat_all(
        input_path=validated_path,
        output_path=os.path.join(output_dir, "fact_result.txt"),
    )

    logger.info(f"========== FACT evaluation completed for {target_model} ==========")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run FACT benchmark pipeline")
    parser.add_argument("target_model", type=str, help="Target model name")
    parser.add_argument('--limit', type=int, default=None, help='Limit on number of prompts to process (for testing).')
    parser.add_argument("--raw_data_dir", type=str, default="data/test_data/raw_data",
                        help="Directory containing raw model outputs")
    parser.add_argument("--query_file", type=str, default="data/prompt_data/query.jsonl",
                        help="Path to query data with language information")
    parser.add_argument("--output_dir", type=str, default="", help="Directory to store FACT benchmark results")
    parser.add_argument("--n_total_process", type=int, default=1, help="Number of parallel processes")

    args = parser.parse_args()

    run_fact_benchmark(
        target_model=args.target_model,
        limit=args.limit,
        raw_data_dir=args.raw_data_dir,
        query_file=args.query_file,
        output_dir=args.output_dir,
        n_total_process=args.n_total_process,
    )
