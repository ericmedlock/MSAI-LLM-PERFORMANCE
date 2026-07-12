#!/bin/bash
# One-shot environment setup for ANY box: detects the platform, builds the
# Python venv, installs deps, runs the offline test suite, bootstraps the
# Ollama model server, and pulls the pinned model. Idempotent — run it as
# often as you like. After it succeeds: bash scripts/run_trials.sh
#
# Usage: bash scripts/setup.sh [model_tag]      (default deepseek-r1:14b)
set -euo pipefail
cd "$(dirname "$0")/.."
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
# CUDA hosts (shadow/hpc/Azure) need the NVML binding for GPU telemetry
# (pynvml, via nvidia-ml-py). It is split out because it does not exist on
# Metal. Without it, peak_vram_mb / gpu_util / gpu_power are silently null.
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[setup] NVIDIA GPU detected — installing CUDA telemetry deps"
  "$VPY" -m pip install -q -r requirements-cuda.txt
fi
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
