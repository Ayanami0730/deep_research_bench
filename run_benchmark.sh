#!/bin/bash
# Target model name list
TARGET_MODELS=("claude-3-7-sonnet-latest")

# Common parameters for both RACE and Citation evaluations
RAW_DATA_DIR="data/test_data/raw_data"
OUTPUT_DIR="results"
N_TOTAL_PROCESS=10
QUERY_DATA_PATH="data/prompt_data/query.jsonl"

# Limit on number of prompts to process (for testing). Uncomment to enable
# LIMIT="--limit 2"

# Skip article cleaning step. Uncomment to enable
# SKIP_CLEANING="--skip_cleaning"

# Only process specific language data. Uncomment to enable
# ONLY_ZH="--only_zh"  # Only process Chinese data
# ONLY_EN="--only_en"  # Only process English data

# Force re-evaluation even if results exist. Uncomment to enable
# FORCE="--force"

# Specify log output file
OUTPUT_LOG_FILE="output.log"

# Clear log file
echo "Starting benchmark tests, log output to: $OUTPUT_LOG_FILE" > "$OUTPUT_LOG_FILE"

# Loop through each model in the target models list
for TARGET_MODEL in "${TARGET_MODELS[@]}"; do
  echo "Running benchmark for target model: $TARGET_MODEL"
  echo -e "\n\n========== Starting evaluation for $TARGET_MODEL ==========\n" >> "$OUTPUT_LOG_FILE"

  # --- Phase 1: RACE Evaluation ---
  echo "==== Phase 1: Running RACE Evaluation for $TARGET_MODEL ====" | tee -a "$OUTPUT_LOG_FILE"
  RACE_OUTPUT="$OUTPUT_DIR/race/$TARGET_MODEL"
  mkdir -p "$RACE_OUTPUT"

  # Build RACE command as an array
  PYTHON_CMD=(python -u deepresearch_bench_race.py "$TARGET_MODEL"
              --raw_data_dir "$RAW_DATA_DIR"
              --max_workers "$N_TOTAL_PROCESS"
              --query_file "$QUERY_DATA_PATH"
              --output_dir "$RACE_OUTPUT")

  # Add optional flags
  [[ -n "$LIMIT" ]] && PYTHON_CMD+=("$LIMIT")
  [[ -n "$SKIP_CLEANING" ]] && PYTHON_CMD+=("$SKIP_CLEANING")
  [[ -n "$ONLY_ZH" ]] && PYTHON_CMD+=("$ONLY_ZH")
  [[ -n "$ONLY_EN" ]] && PYTHON_CMD+=("$ONLY_EN")
  [[ -n "$FORCE" ]] && PYTHON_CMD+=("$FORCE")

  echo "Executing command: ${PYTHON_CMD[*]}" | tee -a "$OUTPUT_LOG_FILE"
  "${PYTHON_CMD[@]}" >> "$OUTPUT_LOG_FILE" 2>&1

  echo "Completed RACE benchmark test for target model: $TARGET_MODEL"
  echo -e "\n========== RACE test completed for $TARGET_MODEL ==========\n" >> "$OUTPUT_LOG_FILE"

  # --- Phase 2: FACT Evaluation ---
  echo "==== Phase 2: Running FACT Evaluation for $TARGET_MODEL ====" | tee -a "$OUTPUT_LOG_FILE"
  CITATION_OUTPUT="$OUTPUT_DIR/fact/$TARGET_MODEL"
  mkdir -p "$CITATION_OUTPUT"

  # Single call to FACT benchmark script
  FACT_CMD=(python -u deepresearch_bench_fact.py "$TARGET_MODEL"
            --raw_data_dir "$RAW_DATA_DIR"
            --query_file "$QUERY_DATA_PATH"
            --output_dir "$OUTPUT_DIR"
            --n_total_process "$N_TOTAL_PROCESS")

  echo "Executing command: ${FACT_CMD[*]}" | tee -a "$OUTPUT_LOG_FILE"
  "${FACT_CMD[@]}" >> "$OUTPUT_LOG_FILE" 2>&1

  echo "Completed FACT benchmark test for target model: $TARGET_MODEL"
  echo -e "\n========== FACT test completed for $TARGET_MODEL ==========\n" >> "$OUTPUT_LOG_FILE"
  echo "--------------------------------------------------"
done

echo "All benchmark tests completed. Logs saved in $OUTPUT_LOG_FILE"
