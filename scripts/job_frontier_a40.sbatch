#!/bin/bash
# UNCC Starlight (SLURM) — frontier-v2.1 confirmatory sweep, pinned to A40.
# One array element per backend => 3 concurrent single-GPU jobs, each with its
# own Ollama server (private port via run_trials.sh) and its own output file.
#
# Submit from the repo root ON A LOGIN NODE (hpc.charlotte.edu), after:
#   bash scripts/setup.sh --download          # once; internet needed (login node has it)
#   sbatch scripts/job_frontier_a40.sbatch
#
# Scaling legs reuse this script with overrides at submit time, e.g.:
#   sbatch --export=ALL,LLM_MODEL=deepseek-r1:32b,MODEL_TAG=deepseek-r1-distill-qwen-32b,TRIALS=2,OUT_PREFIX=results/frontier-v2.1-hpc-32b \
#          scripts/job_frontier_a40.sbatch
#
# Requeue/timeout safe: the harness resumes at row level, so a requeued array
# element just picks up where its output file left off.
#SBATCH --job-name=frontier-v2.1
#SBATCH --partition=GPU
#SBATCH --gres=gpu:A40:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --requeue
#SBATCH --array=0-2
#SBATCH --output=runs/slurm-%A_%a.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?run via sbatch from the repo root}"

BACKENDS=(monolithic agentic swarm)
BACKEND="${BACKENDS[$SLURM_ARRAY_TASK_ID]}"
export OUT="${OUT_PREFIX:-results/frontier-v2.1-hpc-14b}-${BACKEND}.jsonl"

echo "== node: $(hostname)  job: ${SLURM_JOB_ID}  backend: ${BACKEND}"
nvidia-smi -L || true

bash scripts/setup.sh --offline "${LLM_MODEL:-deepseek-r1:14b}"
bash scripts/run_trials.sh hpc --backend "$BACKEND"

echo "== done: $OUT ($(wc -l < "$OUT") rows)"
