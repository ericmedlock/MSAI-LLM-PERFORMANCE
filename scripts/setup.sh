#!/bin/bash
# One-shot environment setup for ANY box: detects the platform, builds the
# Python venv, installs deps, runs the offline test suite, bootstraps the
# Ollama model server, and pulls the pinned model. Idempotent — run it as
# often as you like. After it succeeds: bash scripts/run_trials.sh
#
# Usage: bash scripts/setup.sh [--download|--offline] [model_tag]
#   (no flag)   full setup — laptop/Shadow behavior, unchanged (default deepseek-r1:14b)
#   --download  same full setup; run on a CLUSTER LOGIN NODE (has internet) so all
#               artifacts (venv, ollama binary, model blobs) land on the shared FS
#   --offline   verify-only for CLUSTER COMPUTE NODES (no internet assumed):
#               checks venv + ollama binary + model cache, fails fast with a remedy
set -euo pipefail
cd "$(dirname "$0")/.."

STAGE=full
case "${1:-}" in
  --download) STAGE=download; shift ;;
  --offline)  STAGE=offline;  shift ;;
esac
MODEL="${1:-deepseek-r1:14b}"

# --- 0. detect where we are --------------------------------------------------------
detect_profile() {
  if [ -n "${SLURM_JOB_ID:-}" ] || command -v sbatch >/dev/null 2>&1; then echo hpc; return; fi
  case "$(uname -s)" in
    Darwin) echo local ;;
    MINGW*|MSYS*|CYGWIN*) echo shadow ;;
    Linux) command -v nvidia-smi >/dev/null 2>&1 && echo hpc || echo other ;;
    *) echo other ;;
  esac
}
PROFILE="$(detect_profile)"
echo "[setup] detected profile: $PROFILE  ($(uname -s), GPU: $(command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader | head -1 || echo 'none/Metal'))"

# On a cluster, keep the model cache on scratch, not the quota'd home dir.
# Must match between --download (login node) and jobs; run_trials.sh applies
# the same default so both sides agree without any per-user config.
if [ "$PROFILE" = "hpc" ] && [ -z "${OLLAMA_MODELS:-}" ] && [ -d "/scratch/$USER" ]; then
  export OLLAMA_MODELS="/scratch/$USER/ollama-models"
  echo "[setup] OLLAMA_MODELS defaulted to $OLLAMA_MODELS (home dir is quota'd)"
fi

# --- offline stage: verify artifacts only; no network, no installs ------------------
if [ "$STAGE" = "offline" ]; then
  FAIL=0
  if [ -x ".venv/bin/python" ] || [ -x ".venv/Scripts/python.exe" ]; then
    echo "[setup:offline] venv: OK"
  else
    echo "[setup:offline] venv: MISSING — run 'bash scripts/setup.sh --download' on a login node"; FAIL=1
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if command -v ollama >/dev/null 2>&1; then
    echo "[setup:offline] ollama binary: OK ($(command -v ollama))"
  else
    echo "[setup:offline] ollama binary: MISSING — run 'bash scripts/setup.sh --download' on a login node"; FAIL=1
  fi
  # model blobs live under <cache>/manifests/registry.ollama.ai/library/<name>/<tag>
  CACHE="${OLLAMA_MODELS:-$HOME/.ollama/models}"
  NAME="${MODEL%%:*}"; TAG="${MODEL#*:}"; [ "$TAG" = "$MODEL" ] && TAG=latest
  if [ -f "$CACHE/manifests/registry.ollama.ai/library/$NAME/$TAG" ]; then
    echo "[setup:offline] model cache ($MODEL): OK"
  else
    echo "[setup:offline] model cache ($MODEL): MISSING under $CACHE"
    echo "[setup:offline]   remedy: on a login node: OLLAMA_MODELS=$CACHE bash scripts/setup.sh --download $MODEL"; FAIL=1
  fi
  [ "$FAIL" = 0 ] && echo "[setup:offline] all artifacts present — ready to run" || exit 1
  exit 0
fi

# --- 1. python venv + deps ----------------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  command -v "$c" >/dev/null 2>&1 && PY="$c" && break
done
[ -n "$PY" ] || { echo "[setup] Python 3.11+ required"; exit 1; }
if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
  echo "[setup] creating venv with $PY"
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"; [ -x "$VPY" ] || VPY=".venv/Scripts/python.exe"
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt
echo "[setup] python deps installed"

# --- 2. offline test suite (no model, no GPU, no network) ---------------------------
echo "[setup] offline test suite:"
"$VPY" -m pytest -m "not integration" -q 2>&1 | tail -1

# --- 3. model server + pinned model -------------------------------------------------
bash scripts/bootstrap_model_server.sh "$MODEL"

echo
echo "[setup] DONE. profile=$PROFILE. Next:"
echo "        bash scripts/run_trials.sh            # auto-detected profile ($PROFILE)"
echo "        bash scripts/run_trials.sh shadow     # or force one: shadow|hpc|local"
