#!/bin/bash
# ============================================================================
# A40 DEPLOY-V2 RE-RUN PIPELINE (brief §5 — study integrity rules enforced)
#
#   bash scripts/hpc_a40_v2_rerun.sh probe        # 1) mono x 36 x 1 trial, fixed deployment
#   bash scripts/hpc_a40_v2_rerun.sh probe-check  # 2) GATE: compare vs existing A40 cell
#   bash scripts/hpc_a40_v2_rerun.sh full         # 3) only if gate passed: 15-way full grid
#   bash scripts/hpc_a40_v2_rerun.sh validate     # 4) completeness check + merge + before/after
#
# Run from the repo root on the Starlight login node. All output lands under
# results-HPC/a40-deploy-v2/ — NEVER merged with the as-deployed epoch-2 cell
# (that data stays in the paper as the deployment-properties evidence).
#
# Fixed deployment applied to every job (edit DEPLOY block if diagnostics
# justify different values — and record why in the config diff):
#   --cpus-per-task=8, OLLAMA_FLASH_ATTENTION=1, OLLAMA_NUM_PARALLEL=3,
#   LLM_TIMEOUT_S=1800. Pinned science untouched: temp 0.6, per-trial seed
#   offsets, lenient verdict, frozen frontier-v2.1 manifest.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

V2DIR="results-HPC/a40-deploy-v2"
OLD_CELL="results-HPC/frontier-v2.1-hpc-14b-n5.jsonl"
CANON="$V2DIR/frontier-v2.1-hpc-a40v2-14b-n5.jsonl"
MODE="${1:-}"
mkdir -p "$V2DIR/shards" runs

write_sbatch() {  # $1 = probe|full
  local ARRAY OUTLINE CMD
  if [ "$1" = probe ]; then
    ARRAY="0-0"
    OUTLINE='export OUT="results-HPC/a40-deploy-v2/probe-mono-t1.jsonl"'
    CMD='bash scripts/run_trials.sh hpc --backend monolithic --trial 1'
  else
    ARRAY="0-14"
    OUTLINE='BACKENDS=(monolithic agentic swarm); B=${BACKENDS[$((SLURM_ARRAY_TASK_ID / 5))]}; T=$((SLURM_ARRAY_TASK_ID % 5 + 1)); export OUT="results-HPC/a40-deploy-v2/shards/frontier-v2.1-hpc-a40v2-14b-${B}-t${T}.jsonl"'
    CMD='bash scripts/run_trials.sh hpc --backend "$B" --trial "$T"'
  fi
  cat > runs/a40v2_$1.sbatch << SBATCH
#!/bin/bash
#SBATCH --job-name=a40v2-$1
#SBATCH --partition=GPU
#SBATCH --gres=gpu:A40:1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --requeue
#SBATCH --array=${ARRAY}
#SBATCH --output=runs/slurm-a40v2-$1-%A_%a.out
set -euo pipefail
cd "\${SLURM_SUBMIT_DIR:?submit from the repo root}"
# ---- DEPLOY block (the fix under test; recorded in the sidecar) ----
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_NUM_PARALLEL=3
export LLM_TIMEOUT_S=1800
export AGENTIC_VERDICT=lenient
${OUTLINE}
# ---- deployment characterization sidecar (brief §5 telemetry) ----
SIDE="\${OUT%.jsonl}.deploy.txt"
{ echo "== \$(date) job \${SLURM_JOB_ID} node \$(hostname)";
  scontrol show job "\$SLURM_JOB_ID" | grep -E "CpusPerTask|NumCPUs|Nodelist";
  nvidia-smi -q -d POWER,CLOCK,PCIE | grep -E "Power Limit|SM +:|Link Gen|Link Width" | head -8;
  env | grep -E "OLLAMA_|LLM_TIMEOUT"; } > "\$SIDE" 2>&1
echo "== a40v2 $1: \$OUT"
nvidia-smi -L || true
bash scripts/setup.sh --offline "\${LLM_MODEL:-deepseek-r1:14b}"
${CMD}
echo "== done: \$OUT (\$(wc -l < "\$OUT") rows)"
SBATCH
}

case "$MODE" in
# ---------------------------------------------------------------------------
probe)
  .venv/bin/python -m harness.run --help 2>/dev/null | grep -q -- "--trial" || {
    echo "ABORT: checkout lacks the --trial flag — git pull first."; exit 1; }
  write_sbatch probe
  sbatch runs/a40v2_probe.sbatch
  echo "Probe submitted (mono x 36 tasks x trial 1, ~1-2 h)."
  echo "When it finishes: bash scripts/hpc_a40_v2_rerun.sh probe-check"
  ;;
# ---------------------------------------------------------------------------
probe-check)
  .venv/bin/python - << 'PY'
import json, sys
from collections import defaultdict

def tseed(r): return r.get("trial_seed") or (r.get("metadata") or {}).get("trial_seed")

probe = [json.loads(l) for l in open("results-HPC/a40-deploy-v2/probe-mono-t1.jsonl") if l.strip()]
old = [json.loads(l) for l in open("results-HPC/frontier-v2.1-hpc-14b-n5.jsonl") if l.strip()]
old_mono = [r for r in old if r["backend"] == "monolithic"]
# Same-seed reference: the old cell's OWN trial-1 rows (seed 1042). An N=1
# probe vs the N=5 mean trips on trial-sampling noise alone (verified: the old
# cell's own t1 sits 7.2 pts below its 5-trial mean) — t1-vs-t1 is the fair gate.
old_t1 = [r for r in old_mono if tseed(r) == 1042]

def acc(rows): return sum(r["correct"] for r in rows) / len(rows)
def dom(rows):
    d = defaultdict(list)
    for r in rows: d[r["task_domain"]].append(r["correct"])
    return {k: sum(v)/len(v) for k, v in d.items()}

pa, oa = acc(probe), acc(old_t1)
pd_, od = dom(probe), dom(old_t1)
tokps_p = sum(r.get("tokens_per_s") or 0 for r in probe)/len(probe)
tokps_o = sum(r.get("tokens_per_s") or 0 for r in old_mono)/len(old_mono)
print(f"probe rows: {len(probe)} (expect 36)")
print(f"throughput: {tokps_o:.1f} -> {tokps_p:.1f} tok/s "
      f"({'TARGET MET (>=30)' if tokps_p >= 30 else 'STILL SLOW — fix not landed, investigate before full run'})")
print(f"accuracy vs same-seed t1 reference: {oa:.1%} -> {pa:.1%} "
      f"(old N=5 mean for context: {acc(old_mono):.1%})")
for k in sorted(set(pd_) | set(od)):
    print(f"  {k}: {od.get(k,0):.0%} -> {pd_.get(k,0):.0%}")
delta = abs(pa - oa) * 100
if len(probe) != 36:
    print("GATE: ❌ probe incomplete — rerun/resume it first"); sys.exit(1)
if delta > 8.0:  # ~3 tasks on the same-seed comparison
    print(f"GATE: 🛑 STOP — same-seed accuracy moved {delta:.1f} pts (> 8). The"
          " deployment change may have altered effective difficulty. AUTHOR"
          " DECISION required (re-freeze per §3.2 of the draft) before any"
          " full grid."); sys.exit(2)
print(f"GATE: ✅ PASS (Δ {delta:.1f} pts ≤ 8 vs same-seed t1). Proceed: bash scripts/hpc_a40_v2_rerun.sh full")
PY
  ;;
# ---------------------------------------------------------------------------
full)
  write_sbatch full
  sbatch runs/a40v2_full.sbatch
  echo "Full grid submitted: 15 shards (3 backends x 5 trials), ~3-5 h on 15 A40s."
  echo "When drained: bash scripts/hpc_a40_v2_rerun.sh validate"
  ;;
# ---------------------------------------------------------------------------
validate)
  .venv/bin/python scripts/validate_cell.py "$V2DIR"/shards/*.jsonl --trials 5
  cat "$V2DIR"/shards/*.jsonl > "$CANON"
  echo "merged -> $CANON ($(wc -l < "$CANON") rows)"
  .venv/bin/python - << 'PY'
import json
from collections import defaultdict
new = [json.loads(l) for l in open("results-HPC/a40-deploy-v2/frontier-v2.1-hpc-a40v2-14b-n5.jsonl") if l.strip()]
old = [json.loads(l) for l in open("results-HPC/frontier-v2.1-hpc-14b-n5.jsonl") if l.strip()]
print("\n=== BEFORE/AFTER (as-deployed vs deploy-v2) — brief §6 one-pager ===")
print(f"{'backend':11s} {'acc old->new':>16s} {'tok/s':>13s} {'W':>11s} {'kJ/correct':>16s}")
for b in ("monolithic", "agentic", "swarm"):
    o = [r for r in old if r["backend"] == b]; n = [r for r in new if r["backend"] == b]
    def acc(rs): return sum(r["correct"] for r in rs)/len(rs)*100
    def tps(rs): return sum(r.get("tokens_per_s") or 0 for r in rs)/len(rs)
    def watt(rs):
        v=[r["telemetry"]["gpu_power_w"] for r in rs if r["telemetry"].get("gpu_power_w")]; return sum(v)/len(v)
    def kjc(rs):
        J=sum(r["telemetry"]["gpu_power_w"]*r["latency_s"] for r in rs if r["telemetry"].get("gpu_power_w"))
        c=sum(r["correct"] for r in rs); return J/1000/c if c else 0
    print(f"{b:11s} {acc(o):5.1f} -> {acc(n):5.1f} {tps(o):5.1f} -> {tps(n):5.1f} "
          f"{watt(o):4.0f} -> {watt(n):4.0f} {kjc(o):6.1f} -> {kjc(n):6.1f}")
print("\nCommit: git add results-HPC/a40-deploy-v2 && git commit && git pull --rebase && git push")
PY
  ;;
# ---------------------------------------------------------------------------
*)
  echo "usage: $0 {probe|probe-check|full|validate}"; exit 2 ;;
esac
