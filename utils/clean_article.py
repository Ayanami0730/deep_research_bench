import json
import os
import time
import threading
import concurrent.futures
from tqdm import tqdm
from prompt.clean_prompt import clean_article_prompt_zh, clean_article_prompt_en
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Shared LLM-call concurrency cap. All cleaning calls (any chunk of any article)
# acquire from this semaphore so total inflight LLM requests ≤ LLM_CONCURRENCY.
# Override via env LLM_CONCURRENCY=N. Default 20.
_LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "20"))
_llm_semaphore = threading.Semaphore(_LLM_CONCURRENCY)
logger.info(f"LLM call concurrency cap = {_LLM_CONCURRENCY}")


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
    
    _TRUNCATED = "__TRUNCATED__"

    def _clean_text(self, text, language="zh", max_retries=None):
        """Try to clean text. Returns string (incl. "") on success,
        self._TRUNCATED on output overflow, or None after all retries.
        max_retries kept for signature compatibility but the canonical budget
        is _RETRY_BACKOFFS_S (3 attempts with exponential backoff).
        """
        clean_prompt = self._get_clean_prompt(language)
        user_prompt = clean_prompt.format(article=text)
        backoffs = self._RETRY_BACKOFFS_S

        last_err = None
        for attempt, sleep_s in enumerate([0, *backoffs[:-1]]):
            if sleep_s:
                time.sleep(sleep_s)
            try:
                with _llm_semaphore:
                    result, stop_reason = self.clean_agent.generate(
                        user_prompt=user_prompt, system_prompt="",
                        return_metadata=True, stage="clean",
                    )
                if stop_reason in ("max_tokens", "length"):
                    logger.warning(f"Output truncated (stop_reason={stop_reason}), needs chunking")
                    return self._TRUNCATED
                # Accept any string (including "") — empty means the chunk
                # was entirely a reference list, per prompt contract.
                if result is not None:
                    return result
                logger.warning(f"Got None from API, attempt {attempt+1}/{len(backoffs)}")
            except Exception as e:
                last_err = e
                logger.error(f"API call error (attempt {attempt+1}/{len(backoffs)}): {e}")
                if self._is_token_limit_error(e):
                    logger.info("Article too long, needs chunking")
                    return self._TRUNCATED

        logger.error(f"Cleaning failed after {len(backoffs)} attempts; last error: {last_err}")
        return None
        
    @staticmethod
    def _split_at_boundary(text, target_pos):
        """Find nearest sentence boundary to target_pos."""
        search_start = max(0, target_pos - 200)
        for j in range(target_pos, search_start, -1):
            if j < len(text) and text[j] in '.?!。？！\n':
                return j + 1
        return target_pos

    # Pre-chunking thresholds (tokens). One chunk per 50k tokens; <=50k stays whole.
    # 50k leaves headroom under GPT-5.5's output cap for reasoning + cleaned text.
    _CHUNK_TOKEN_STEP = 50_000
    _SPLIT_SEARCH_RADIUS = 5000

    # Per-call retry budget when API throws (excluding fatal errors that signal
    # truncation or token limit, which short-circuit to recursive chunking).
    _RETRY_BACKOFFS_S = (2, 5, 15)

    @staticmethod
    def _estimate_tokens(text, language):
        """Cheap upper-bound token estimate.
        zh: 1 char ≈ 1 token (slight over-est, safer).
        en: 1 token ≈ 3.5 chars.
        """
        if not text:
            return 0
        if language == "zh":
            return len(text)
        return int(len(text) / 3.5) + 1

    @classmethod
    def _compute_num_chunks(cls, num_tokens):
        """Boundaries at 100k, 200k, 300k, ...
        <=100k → 1, (100k,200k] → 2, (200k,300k] → 3, ...
        """
        if num_tokens <= cls._CHUNK_TOKEN_STEP:
            return 1
        # ceil(num_tokens / step)
        return (num_tokens + cls._CHUNK_TOKEN_STEP - 1) // cls._CHUNK_TOKEN_STEP

    @classmethod
    def _find_double_newline_split(cls, text, target_pos, radius=None):
        """Find split position nearest to target_pos.
        Prefers '\\n\\n' (split AFTER the blank line); falls back to '\\n';
        last resort: hard cut at target_pos.
        """
        if radius is None:
            radius = cls._SPLIT_SEARCH_RADIUS
        n = len(text)
        lo = max(0, target_pos - radius)
        hi = min(n, target_pos + radius)

        best_pos, best_dist = None, None
        scan = lo
        while scan < hi:
            idx = text.find("\n\n", scan, hi)
            if idx == -1:
                break
            dist = abs(idx - target_pos)
            if best_dist is None or dist < best_dist:
                best_dist, best_pos = dist, idx + 2
            scan = idx + 1
        if best_pos is not None:
            return best_pos

        # Fallback: nearest single '\n'
        best_pos, best_dist = None, None
        for i in range(lo, hi):
            if text[i] == "\n":
                dist = abs(i - target_pos)
                if best_dist is None or dist < best_dist:
                    best_dist, best_pos = dist, i + 1
        if best_pos is not None:
            return best_pos

        return target_pos

    @classmethod
    def _split_into_chunks(cls, text, num_chunks):
        """Split text into num_chunks pieces at \\n\\n boundaries near i/N positions."""
        if num_chunks <= 1 or not text:
            return [text]
        n = len(text)
        cuts = []
        for i in range(1, num_chunks):
            target = (n * i) // num_chunks
            cuts.append(cls._find_double_newline_split(text, target))
        # Ensure cuts are strictly increasing (paranoid: search radii could overlap)
        cuts = sorted(set(cuts))

        chunks, prev = [], 0
        for c in cuts:
            if c > prev:
                chunks.append(text[prev:c])
                prev = c
        chunks.append(text[prev:])
        return [c for c in chunks if c]

    def _clean_one_chunk(self, idx, total, chunk, language, max_retries):
        """Clean a single pre-split chunk. Returns text or None on failure.
        LLM-call concurrency is gated by the module-level _llm_semaphore inside _clean_text.
        """
        t0 = time.time()
        result = self._clean_text(chunk, language, max_retries)
        if result == self._TRUNCATED:
            logger.info(f"Chunk {idx+1}/{total} still truncated, recursive split")
            result = self.chunk_clean_article(chunk, language)
        if not result:
            logger.error(f"Chunk {idx+1}/{total} failed to clean")
            return None
        logger.info(f"Chunk {idx+1}/{total} cleaned in {time.time()-t0:.1f}s "
                    f"(in={len(chunk):,} out={len(result):,} chars)")
        return result

    def _clean_chunked(self, article, num_chunks, language, max_retries):
        """Pre-split into num_chunks pieces, clean each in parallel, concatenate.
        Concurrent LLM calls across all chunks (and articles) are capped by
        the module-level semaphore.
        """
        chunks = self._split_into_chunks(article, num_chunks)
        logger.info(f"Pre-chunking into {len(chunks)} pieces "
                    f"(sizes: {[len(c) for c in chunks]} chars)")

        # Submit all chunks; semaphore inside _clean_text enforces global cap.
        results = [None] * len(chunks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(chunks)) as ex:
            future_to_idx = {
                ex.submit(self._clean_one_chunk, i, len(chunks), c, language, max_retries): i
                for i, c in enumerate(chunks)
            }
            for fut in concurrent.futures.as_completed(future_to_idx):
                i = future_to_idx[fut]
                results[i] = fut.result()

        if any(r is None for r in results):
            return None
        merged = "".join(results)
        return merged if self._is_valid_result(merged) else None

    def chunk_clean_article(self, article, language="zh", max_depth=3, _depth=0):
        """Recursively split and clean. If a half is truncated, split it again."""
        if _depth >= max_depth:
            logger.warning(f"Max chunk depth {max_depth} reached, giving up")
            return None

        mid = self._split_at_boundary(article, len(article) // 2)
        halves = [article[:mid], article[mid:]]
        cleaned_parts = []

        for i, half in enumerate(halves):
            if not half.strip():
                continue
            result = self._clean_text(half, language)
            if result == self._TRUNCATED:
                logger.info(f"depth={_depth} half={i} truncated, splitting further")
                result = self.chunk_clean_article(half, language, max_depth, _depth + 1)
            if result is None:
                logger.error(f"depth={_depth} half={i} failed")
                return None
            cleaned_parts.append(result)

        merged = "".join(cleaned_parts)
        if self._is_valid_result(merged):
            return merged
        return None
        
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
            
            # Decide chunking up-front based on estimated token count
            est_tokens = self._estimate_tokens(article, language)
            num_chunks = self._compute_num_chunks(est_tokens)
            if num_chunks > 1:
                logger.info(f"ID: {item_id} - Estimated ~{est_tokens:,} tokens, "
                            f"pre-chunking into {num_chunks} pieces")
                cleaned_article = self._clean_chunked(article, num_chunks, language, max_retries)
            else:
                cleaned_article = self._clean_text(article, language, max_retries)

            # Reactive fallback: estimate was off / single-shot got truncated
            if cleaned_article == self._TRUNCATED or cleaned_article is None:
                reason = "truncated" if cleaned_article == self._TRUNCATED else "failed"
                logger.info(f"ID: {item_id} - Cleaning {reason}, falling back to recursive chunking")
                cleaned_article = self.chunk_clean_article(article, language=language)
            
            # If cleaning failed, return error
            if not self._is_valid_result(cleaned_article):
                logger.error(f"ID: {item_id} - Failed to clean article after {max_retries} retries")
                self._update_progress(pbar, pbar_lock)
                return {"id": item_id, "error": "Failed to clean article"}
            
            # Build output data
            result = {
                "id": item_id,
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
            
    def clean_articles(self, model, raw_data_dir, cleaned_data_dir, max_workers=5, max_retries=5, 
                       limit=None, language="en", task_ids=None):
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
            task_ids: Optional set of task IDs to process (filters before limit)
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
        
        # Filter by task_ids if provided
        if task_ids is not None:
            all_items = [item for item in all_items if item.get('id') in task_ids]
        
        # Apply limit
        if limit is not None and limit > 0:
            all_items = all_items[:limit]
            
        # Set of processed IDs for deduplication
        processed_ids = self._load_processed_ids(output_file)
            
        # Filter items that need processing
        to_process = [item for item in all_items if item.get('id') not in processed_ids]
        logger.info(f"Total: {len(all_items)} items, {len(to_process)} to process, {len(processed_ids)} already processed")
        
        # If all items already processed, return
        if not to_process:
            logger.info("All items already processed, no further action needed")
            return
            
        # Create thread locks
        file_lock = threading.Lock()
        pbar_lock = threading.Lock()
        
        # Create progress bar
        failures = []  # list of {id, error}
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
                    if isinstance(result, dict) and result.get("error"):
                        failures.append(result)
                    elif result:
                        processed_count += 1

        if failures:
            failure_path = os.path.join(cleaned_data_dir, f"{model}.clean_failures.jsonl")
            with open(failure_path, "w", encoding="utf-8") as f:
                for fail in failures:
                    f.write(json.dumps(fail, ensure_ascii=False) + "\n")
            logger.error(f"=== {model}: {len(failures)} articles failed cleaning, list saved to {failure_path} ===")

        logger.info(f"=== {model} cleaning complete: {processed_count} new ok, {len(failures)} failed, "
                    f"{len(processed_ids)} total processed ===")

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




