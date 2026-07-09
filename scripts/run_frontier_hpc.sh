#!/bin/bash
# Frontier-v2 sweep, HPC edition. Self-contained per-node job:
# starts an OpenAI-compatible model server, waits for health, runs the harness.
# Row-level checkpointing means jobs can be requeued/resumed freely — rerunning
# the same command tops up only missing rows.
#
# Usage (one model per job):
#   MODEL_GGUF=/path/to/model.gguf MODEL_TAG=deepseek-r1-14b-distill-q4_k_m \
#     OUT=results/frontier-v2-14b.jsonl BACKENDS="monolithic agentic swarm" TRIALS=5 \
#     bash scripts/run_frontier_hpc.sh
#
# Requires: python3.11+ venv with requirements.txt; llama-server (llama.cpp) on PATH
# (or set SERVER_CMD to your own launch command exposing an OpenAI-compatible API).
set -euo pipefail
cd "$(dirname "$0")/.."

: "${MODEL_GGUF:?path to GGUF file}"
: "${MODEL_TAG:?canonical model tag for provenance}"
: "${OUT:?output JSONL path}"
BACKENDS="${BACKENDS:-monolithic agentic swarm}"
TRIALS="${TRIALS:-5}"
PORT="${PORT:-8080}"
MANIFEST="${MANIFEST:-tasks/frontier_v2_manifest.json}"
PYTHON="${PYTHON:-./.venv/bin/python}"

# --- 1. model server (llama.cpp; ctx must cover num_ctx=8192) -------------------
SERVER_CMD="${SERVER_CMD:-llama-server -m "$MODEL_GGUF" -c 8192 -ngl 999 --port "$PORT"}"
echo "[hpc] starting model server: $SERVER_CMD"
$SERVER_CMD &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for i in $(seq 1 120); do
  curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null && break
  [ "$i" = 120 ] && { echo "[hpc] server never became healthy"; exit 1; }
  sleep 5
done
echo "[hpc] server healthy on :$PORT"

# --- 2. harness (env overrides only; pinned science stays in config.yaml) ------
export LLM_PROVIDER=openai
export LLM_BASE_URL="http://127.0.0.1:${PORT}/v1"
export LLM_API_KEY=local
export LLM_MODEL="$MODEL_TAG"
export MODEL_TAG

BACKEND_FLAGS=""
for b in $BACKENDS; do BACKEND_FLAGS="$BACKEND_FLAGS --backend $b"; done

echo "[hpc] running: manifest=$MANIFEST trials=$TRIALS backends=[$BACKENDS] -> $OUT"
"$PYTHON" -m harness.run --manifest "$MANIFEST" $BACKEND_FLAGS --trials "$TRIALS" --output "$OUT"
echo "[hpc] done; rows:"
wc -l "$OUT"
