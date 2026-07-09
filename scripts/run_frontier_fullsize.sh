#!/bin/zsh
# Frontier-external benchmark sweep against full-sized models, sequentially.
# 22 tasks x 3 backends x N=5 = 330 runs per model. Runner is idempotent/resumable.
set -uo pipefail
cd "$(dirname "$0")/.."

export LLM_PROVIDER=openai
export LLM_BASE_URL=http://localhost:1234/v1
export LLM_API_KEY=lm-studio
LMS=$(command -v lms || echo "$HOME/.lmstudio/bin/lms")

run_model() {
  local model="$1" tag="$2" out="$3"
  echo "=============================================================="
  echo "[$(date '+%F %T')] MODEL: $model -> $out"
  echo "=============================================================="
  "$LMS" unload --all
  "$LMS" load "$model" --context-length 8192 -y 2>/dev/null | tail -2
  LLM_MODEL="$model" MODEL_TAG="$tag" \
    ./.venv/bin/python -m harness.run \
      --manifest tasks/frontier_external_manifest.json \
      --output "$out"
  local rc=$?
  echo "[$(date '+%F %T')] DONE $model (exit $rc); rows so far:"
  wc -l "$out" 2>/dev/null || echo "  (no output file)"
  return 0   # continue to next model even if one fails; runner is resumable
}

run_model "deepseek-r1-distill-qwen-32b" "deepseek-r1-distill-qwen-32b" "results/frontier-external-32b.jsonl"
run_model "qwen/qwen3.6-35b-a3b"        "qwen3.6-35b-a3b"              "results/frontier-external-qwen3.6-35b.jsonl"

"$LMS" unload --all
echo "[$(date '+%F %T')] SWEEP COMPLETE"
