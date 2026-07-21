#!/bin/bash
# ============================================================================
# A40 DEPLOYMENT ANOMALY — DIAGNOSTIC BUNDLE (brief §3, 2026-07-21)
#
#   sbatch scripts/hpc_a40_diagnose.sbatch        # from the repo root, login node
#
# Runs the full ranked-cause protocol on one A40 node and writes EVERYTHING to
# results-HPC/diagnostics/<jobid>/ , ending with an auto-summary that walks the
# decision tree (llama-bench fast -> Ollama config; slow -> node config).
# Read-only: changes nothing about the deployment; safe to run any time.
# NOTE: requests generous CPU deliberately (8) so the diagnosis itself is not
# CPU-starved; compare against the historical anomaly jobs' allocation.
# ============================================================================
#SBATCH --job-name=a40-diagnose
#SBATCH --partition=GPU
#SBATCH --gres=gpu:A40:1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=runs/slurm-a40-diagnose-%j.out
set -uo pipefail   # NOT -e: every probe is best-effort; partial bundles are useful
cd "${SLURM_SUBMIT_DIR:?submit from the repo root}"

D="results-HPC/diagnostics/${SLURM_JOB_ID}"
mkdir -p "$D"
MODEL="${LLM_MODEL:-deepseek-r1:14b}"
PORT=$(( 20000 + RANDOM % 20000 ))
export OLLAMA_HOST="127.0.0.1:${PORT}"

log() { echo "== $*" | tee -a "$D/SUMMARY.txt"; }

# ---------- A. environment snapshot ----------------------------------------
log "A. environment snapshot"
scontrol show job "$SLURM_JOB_ID"                    > "$D/scontrol_job.txt" 2>&1
grep -E "CpusPerTask|NumCPUs|TresPerNode|Nodelist"     "$D/scontrol_job.txt" | tee -a "$D/SUMMARY.txt"
nvidia-smi -q -d POWER,CLOCK,PCIE,UTILIZATION,MEMORY > "$D/nvidia_smi_q.txt" 2>&1
nvidia-smi -q | grep -i -A2 mig                      > "$D/mig_check.txt" 2>&1
grep -E "Power Limit|Max Clocks -|^ *SM +:|Link Width|Link Gen" "$D/nvidia_smi_q.txt" | head -12 | tee -a "$D/SUMMARY.txt"
env | grep -i -E "ollama|llm_"                       > "$D/env_ollama.txt" 2>&1
cat /proc/cpuinfo | grep -c processor                > "$D/visible_cpus.txt"
log "visible CPUs in cgroup: $(cat "$D/visible_cpus.txt")"

# ---------- B. start a private Ollama with logged output --------------------
log "B. private Ollama server (port ${PORT}), offload report"
bash scripts/setup.sh --offline "$MODEL" > "$D/setup.log" 2>&1 || true
ollama serve > "$D/ollama_server.log" 2>&1 &
SERVER_PID=$!
for i in $(seq 1 30); do curl -s -m 2 "http://${OLLAMA_HOST}/api/version" >/dev/null && break; sleep 2; done
curl -s "http://${OLLAMA_HOST}/api/version" | tee -a "$D/SUMMARY.txt"; echo

# warm the model, then capture placement + offload evidence
curl -s "http://${OLLAMA_HOST}/api/generate" -d "{\"model\":\"${MODEL}\",\"prompt\":\"hi\",\"stream\":false,\"options\":{\"num_predict\":8}}" >/dev/null
ollama ps > "$D/ollama_ps.txt" 2>&1
cat "$D/ollama_ps.txt" | tee -a "$D/SUMMARY.txt"
grep -i -E "offload|layers|vram" "$D/ollama_server.log" | tail -20 > "$D/offload_report.txt"

# ---------- C. single-stream throughput under dmon + CPU watch --------------
log "C. single-stream generation with live GPU/CPU monitoring"
nvidia-smi dmon -s pucm -d 1 > "$D/dmon.txt" 2>&1 &
DMON_PID=$!
( for i in $(seq 1 90); do ps -o %cpu=,rss= -p "$(pgrep -f 'ollama runner' | head -1)" 2>/dev/null; sleep 1; done ) > "$D/runner_cpu.txt" 2>&1 &
CPUW_PID=$!
GEN=$(curl -s -m 900 "http://${OLLAMA_HOST}/api/generate" -d "{\"model\":\"${MODEL}\",\"prompt\":\"Explain the Chinese Remainder Theorem and give a fully worked example with three congruences.\",\"stream\":false,\"options\":{\"num_predict\":512,\"num_ctx\":8192,\"temperature\":0.6,\"seed\":42}}")
kill $DMON_PID $CPUW_PID 2>/dev/null
echo "$GEN" > "$D/single_stream_raw.json"
TOKS=$(echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(round(d['eval_count']/(d['eval_duration']/1e9),1))" 2>/dev/null)
log "single-stream throughput: ${TOKS:-PARSE-FAIL} tok/s  (anomaly baseline: 17.5; healthy target: >=30)"
awk 'NR>2 {sm+=$5; pw+=$2; n++} END {if(n) printf "dmon means: power %.0f W, SM clock col5 %.0f\n", pw/n, sm/n}' "$D/dmon.txt" | tee -a "$D/SUMMARY.txt"

# ---------- D. hardware isolation: llama-bench on the raw GGUF --------------
log "D. llama-bench isolation (Ollama out of the loop)"
if command -v llama-bench >/dev/null; then
  GGUF=$(ls -S "$HOME/.ollama/models/blobs" 2>/dev/null | head -1)
  if [ -n "$GGUF" ]; then
    llama-bench -m "$HOME/.ollama/models/blobs/$GGUF" -ngl 99 -p 512 -n 128 > "$D/llama_bench.txt" 2>&1
    tail -5 "$D/llama_bench.txt" | tee -a "$D/SUMMARY.txt"
  else
    log "  SKIP: no GGUF blob found under ~/.ollama/models/blobs"
  fi
else
  log "  SKIP: llama-bench not installed. To close the hardware-vs-deployment"
  log "  question, build llama.cpp once on the login node (cmake -B build &&"
  log "  cmake --build build -j) and re-run this diagnostic."
fi

# ---------- E. concurrency: 1 stream vs 3 (the swarm pattern) ---------------
log "E. concurrency test (OLLAMA_NUM_PARALLEL currently: ${OLLAMA_NUM_PARALLEL:-unset/default})"
CONC_PROMPT="{\"model\":\"${MODEL}\",\"prompt\":\"Count from 1 to 50 with a fact about each number.\",\"stream\":false,\"options\":{\"num_predict\":256,\"num_ctx\":8192,\"temperature\":0.6,\"seed\":SEED}}"
T0=$(date +%s)
for s in 101 102 103; do
  curl -s -m 900 "http://${OLLAMA_HOST}/api/generate" -d "${CONC_PROMPT/SEED/$s}" > "$D/conc_$s.json" &
done
wait
T1=$(date +%s)
python3 - "$D" $((T1-T0)) << 'PY' | tee -a "$D/SUMMARY.txt"
import json, sys, glob
d, wall = sys.argv[1], int(sys.argv[2])
per = []
for f in glob.glob(f"{d}/conc_*.json"):
    try:
        j = json.load(open(f))
        per.append(j["eval_count"] / (j["eval_duration"] / 1e9))
    except Exception:
        per.append(0)
tot = sum(j and json.load(open(f)).get("eval_count", 0) for f in glob.glob(f"{d}/conc_*.json") for j in [1])
print(f"3-stream wall: {wall}s | per-stream tok/s: {[round(x,1) for x in per]}")
print("verdict: SERIALIZED (peers queue; B6 risk without long timeouts)" if wall > 150 else "verdict: overlapping")
PY

kill $SERVER_PID 2>/dev/null

# ---------- F. auto decision-tree summary -----------------------------------
log "F. DECISION TREE (read with brief §2 ranking)"
log "  1. CpusPerTask low (<8)?           -> Slurm CPU starvation: raise --cpus-per-task"
log "  2. ollama ps not '100% GPU'?       -> partial offload: fix num_gpu/VRAM pressure"
log "  3. llama-bench >=35 tok/s but      "
log "     single-stream <25?              -> Ollama deployment config is the problem"
log "  4. llama-bench also slow?          -> node: clocks/power cap/PCIe/contention"
log "  5. SM clock << 1740 MHz under load? -> power cap or P-state issue"
log "Bundle: $D — commit it (results-HPC/ is the capture zone) and hand to analysis."
echo "DONE"
