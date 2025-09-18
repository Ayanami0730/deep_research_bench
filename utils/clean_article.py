import concurrent.futures
import json
import logging
import os
import threading

from tqdm import tqdm

from prompt.clean_prompt import clean_article_prompt_zh, clean_article_prompt_en

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ArticleCleaner:
    def __init__(self, clean_agent):
        self.clean_agent = clean_agent
        self.min_valid_length = 100

    def _get_clean_prompt(self, language="zh"):
        """Return language-specific cleaning prompt template"""
        return clean_article_prompt_zh if language == "zh" else clean_article_prompt_en

    def _is_valid_result(self, text):
        """Check if cleaning result is valid"""
        return text and len(text.strip()) >= self.min_valid_length

    def _update_progress(self, pbar, pbar_lock):
        """Update progress bar safely"""
        if pbar and pbar_lock:
            with pbar_lock:
                pbar.update(1)

    def _is_token_limit_error(self, error):
        """Check if error is related to token limit"""
        error_str = str(error).lower()
        return "tokens" in error_str and "less than" in error_str

    def _clean_text(self, text, language="zh", max_retries=3):
        """Try to clean text, handle API errors and retry logic"""
        clean_prompt = self._get_clean_prompt(language)
        user_prompt = clean_prompt.format(article=text)

        for retry in range(max_retries):
            try:
                result = self.clean_agent.generate(user_prompt=user_prompt, system_prompt="")
                if self._is_valid_result(result):
                    return result
                logger.warning(f"Invalid cleaning result, retry #{retry + 1}")
            except Exception as e:
                logger.error(f"API call error: {e}")
                if self._is_token_limit_error(e):
                    logger.info(f"Article too long, needs chunking")
                    return None

        return None

    def chunk_clean_article(self, article, language="zh"):
        """
        Split long article into two chunks for processing, then combine results.
        Returns None if processing fails.
        """
        logger.info("Attempting to process article in 2 chunks")

        # Split article
        chunks = []
        chunk_size = len(article) // 2

        for i in range(2):
            start = i * chunk_size
            # Last chunk goes to end of article
            end = len(article) if i == 1 else chunk_size

            # Split at sentence boundaries (first chunk only)
            if i == 0:
                # Look for sentence boundaries near chunk_size
                search_start = max(0, end - 200)

                for j in range(end, search_start, -1):
                    if j < len(article) and article[j] in ['.', '?', '!', '。', '？', '！', '\n']:
                        end = j + 1
                        break

            chunk = article[start:end]
            chunks.append(chunk)

        # Clean each chunk
        cleaned_chunks = []

        for i, chunk in enumerate(chunks):
            try:
                clean_result = self._clean_text(chunk, language)

                # If returns None, indicates token limit error
                if clean_result is None and len(chunk) > 200000:
                    logger.error(f"Chunk {i + 1} too large, cannot process")
                    return None

                cleaned_chunks.append(clean_result)

            except Exception as e:
                logger.error(f"Failed to clean chunk {i + 1}/2: {e}")
                return None

        # Merge results
        logger.info("All chunks processed, merging results")
        merged_article = "".join(cleaned_chunks)
        return merged_article

    def clean_single(self, item, output_file=None, processed_ids=None, file_lock=None,
                     pbar_lock=None, pbar=None, max_retries=5, language="zh"):
        """
        Clean a single article
        """
        if not self.clean_agent:
            logger.error("No clean_agent provided, cannot clean article")
            self._update_progress(pbar, pbar_lock)
            return None

        try:
            data = item.copy()
            item_id = data.get('id')
            prompt = data.get('prompt', '')
            article = data.get('article', '')

            # Skip if missing required fields or already processed
            if not item_id or not prompt or not article:
                self._update_progress(pbar, pbar_lock)
                return None

            if processed_ids is not None and item_id in processed_ids:
                self._update_progress(pbar, pbar_lock)
                return None

            # Try to clean article
            cleaned_article = self._clean_text(article, language, max_retries)

            # If _clean_text returns None, possible token limit error, try chunking
            if cleaned_article is None:
                logger.info(f"ID: {item_id} - Article may be too long, trying chunked processing")
                cleaned_article = self.chunk_clean_article(article, language=language)

            # If cleaning failed, return error
            if not self._is_valid_result(cleaned_article):
                logger.error(f"ID: {item_id} - Failed to clean article after {max_retries} retries")
                self._update_progress(pbar, pbar_lock)
                return {"id": item_id, "error": "Failed to clean article"}

            # Build output data
            result = {
                "id": item_id,
                "language": language,
                "prompt": prompt,
                "article": cleaned_article
            }

            # If output parameters provided, write to file
            if output_file and file_lock and processed_ids is not None:
                self._write_result_to_file(result, output_file, file_lock, processed_ids, item_id)
                self._update_progress(pbar, pbar_lock)
                return item_id
            else:
                self._update_progress(pbar, pbar_lock)
                return result

        except Exception as e:
            self._update_progress(pbar, pbar_lock)
            logger.error(f"Error cleaning article {item.get('id', 'unknown')}: {e}")
            return None

    def _write_result_to_file(self, result, output_file, file_lock, processed_ids, item_id):
        """Write result to file and update processed IDs set"""
        with file_lock:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
            processed_ids.add(item_id)

    def clean_articles(self, model: str, raw_data_dir: str, cleaned_data_dir: str, max_workers: int = 5,
                       max_retries: int = 5, limit=None, language: str = "en"):
        """
        Clean articles for a single model

        Args:
            model: Model name
            raw_data_dir: Raw data directory
            cleaned_data_dir: Cleaned data directory
            max_workers: Maximum thread count
            max_retries: Maximum retry attempts
            limit: Limit on number of items to process
            language: Article language (zh or en)
        """
        # Ensure output directory exists
        os.makedirs(cleaned_data_dir, exist_ok=True)

        input_file = os.path.join(raw_data_dir, f"{model}.jsonl")
        output_file = os.path.join(cleaned_data_dir, f"{model}.jsonl")

        if not os.path.exists(input_file):
            logger.warning(f"Input file for model {model} not found: {input_file}")
            return

        logger.info(f"=== Cleaning {model} articles ===")

        # Load input data
        all_items = self._load_items(input_file)

        # Apply language filtering
        if language:
            all_items = [item for item in all_items if item.get('language', 'en') == language]

        # Apply limit
        if limit is not None and limit > 0:
            all_items = all_items[:limit]

        # Set of processed IDs for deduplication
        processed_ids = self._load_processed_ids(output_file)

        # Filter items that need processing
        to_process = [item for item in all_items if item.get('id') not in processed_ids]
        logger.info(
            f"Total: {len(all_items)} items, {len(to_process)} to process, {len(processed_ids)} already processed")

        # If all items already processed, return
        if not to_process:
            logger.info("All items already processed, no further action needed")
            return

        # Create thread locks
        file_lock = threading.Lock()
        pbar_lock = threading.Lock()

        # Create progress bar
        with tqdm(total=len(all_items), desc=f"Cleaning {model} articles", initial=len(processed_ids)) as pbar:
            # Multi-threaded processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit tasks
                futures = []
                for item in to_process:
                    future = executor.submit(
                        self.clean_single, item, output_file, processed_ids,
                        file_lock, pbar_lock, pbar, max_retries=max_retries, language=language
                    )
                    futures.append(future)

                # Wait for all tasks to complete
                processed_count = 0
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        processed_count += 1

        logger.info(
            f"=== {model} model cleaning complete, cleaned {processed_count} new articles, total of {len(processed_ids)} articles processed ===")

    def _load_items(self, input_file):
        """Load items from input file"""
        all_items = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        all_items.append(item)
                    except json.JSONDecodeError:
                        logger.warning(f"Error parsing JSON in input file, line: {line.strip()}")
        return all_items

    def _load_processed_ids(self, output_file):
        """Load already processed IDs"""
        processed_ids = set()

        # If output file exists, read already processed IDs
        if os.path.exists(output_file):
            logger.info(f"Found existing output file: {output_file}")
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if 'id' in data:
                                processed_ids.add(data['id'])
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON line in output file, skipped")
            logger.info(f"Read {len(processed_ids)} already processed records from output file")
        else:
            # Create empty file
            open(output_file, 'w', encoding='utf-8').close()
            logger.info(f"Created new output file: {output_file}")

        return processed_ids
