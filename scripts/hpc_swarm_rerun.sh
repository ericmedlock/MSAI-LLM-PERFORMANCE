#!/bin/bash
# ============================================================================
# SWARM SHARD RE-RUN — Starlight/HPC, one command, all parameters pre-set.
#
#   bash scripts/hpc_swarm_rerun.sh            # quarantine + submit (default)
#   bash scripts/hpc_swarm_rerun.sh validate   # after jobs finish: check + merge
#
# Run from the repo root on a LOGIN NODE (hpc.charlotte.edu).
#
# WHAT / WHY: the 2026-07-15 array left the swarm cell unusable — bug B6
# (LLM_TIMEOUT_S not exported; peers queueing on OLLAMA_NUM_PARALLEL=1 burned
# the 600 s client default; 65/180 rows backend_exception). This script
# re-runs ONLY the 5 swarm trial-shards under the amended config with the fix
# baked in. Mono + agentic shards are complete — do not touch them.
#
# REQUIREMENT: this repo checkout must include the --trial harness flag
# (commit "feat(harness): --trial slice flag", 2026-07-17). The script
# preflights this and refuses to submit without it — if it refuses, sync the
# repo from GitHub via your usual manual transfer first.
#
# Full context: docs/HPC_RERUN_HANDOFF.md (2026-07-17 addendum) and
# results/POST_RUN_NOTE_2026-07-15_swarm_read_timeout.md.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

SHARD_DIR="results-HPC/hpc-shards"
PREFIX="$SHARD_DIR/frontier-v2.1-hpc-14b-swarm-t"
CANON="results-HPC/frontier-v2.1-hpc-14b-n5.jsonl"
EXPECT_HASH="2bdbb6952605c7ca"
MODE="${1:-run}"

# ---------------------------------------------------------------------------
preflight() {
  command -v sbatch >/dev/null || { echo "ABORT: no sbatch — run this on the HPC login node."; exit 1; }
  [ -f tasks/frontier_v2_1_manifest.json ] || { echo "ABORT: run from the repo root."; exit 1; }
  grep -q "temperature: 0.6" config/config.yaml || {
    echo "ABORT: config/config.yaml lacks 'temperature: 0.6' — this checkout predates"
    echo "Amendment 2026-07-15. Sync the repo before running."; exit 1; }
  .venv/bin/python -m harness.run --help 2>/dev/null | grep -q -- "--trial" || {
    echo "ABORT: this checkout's harness has no --trial flag — sync the repo"
    echo "(needs the 2026-07-17 'trial slice' commit)."; exit 1; }
}

# ---------------------------------------------------------------------------
submit() {
  preflight
  echo "== quarantining poisoned swarm shards (row-resume would keep dead rows) =="
  local STAMP; STAMP="$(date +%Y%m%d%H%M%S)"
  for t in 1 2 3 4 5; do
    if [ -f "${PREFIX}${t}.jsonl" ]; then
      mv -v "${PREFIX}${t}.jsonl" "${PREFIX}${t}.jsonl.POISONED-B6.${STAMP}"
    fi
  done

  mkdir -p runs
  cat > runs/swarm_rerun.sbatch << 'SBATCH'
#!/bin/bash
#SBATCH --job-name=swarm-rerun
#SBATCH --partition=GPU
#SBATCH --gres=gpu:A40:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --requeue
#SBATCH --array=0-4
#SBATCH --output=runs/slurm-swarm-rerun-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?submit from the repo root}"

TRIAL=$((SLURM_ARRAY_TASK_ID + 1))
export OUT="results-HPC/hpc-shards/frontier-v2.1-hpc-14b-swarm-t${TRIAL}.jsonl"
export LLM_TIMEOUT_S=1800          # bug B6 fix — the entire reason for this re-run
export OLLAMA_NUM_PARALLEL=1       # pinned serving topology (matches M5/M4)
export AGENTIC_VERDICT=lenient     # epoch-2 convention (no-op for swarm; uniformity)

echo "== node: $(hostname)  job: ${SLURM_JOB_ID}  swarm trial ${TRIAL}"
nvidia-smi -L || true
bash scripts/setup.sh --offline "${LLM_MODEL:-deepseek-r1:14b}"
bash scripts/run_trials.sh hpc --backend swarm --trial "${TRIAL}"
echo "== done: $OUT ($(wc -l < "$OUT") rows)"
SBATCH

  echo "== submitting 5-element array (one A40 + private Ollama per trial shard) =="
  sbatch runs/swarm_rerun.sbatch
  echo ""
  echo "Monitor:  squeue -u \$USER"
  echo "When all 5 finish: bash scripts/hpc_swarm_rerun.sh validate"
}

# ---------------------------------------------------------------------------
validate() {
  .venv/bin/python - << PY
import json, sys
from collections import Counter

hash_want = "${EXPECT_HASH}"
bad = False
all_rows = []
for b in ("monolithic", "agentic", "swarm"):
    for t in range(1, 6):
        p = f"${SHARD_DIR}/frontier-v2.1-hpc-14b-{b}-t{t}.jsonl"
        try:
            rows = [json.loads(l) for l in open(p) if l.strip()]
        except FileNotFoundError:
            print(f"MISSING  {p}"); bad = True; continue
        exc = sum(1 for r in rows if r.get("error_category") == "backend_exception")
        hashes = set(r["config_hash"] for r in rows)
        power = sum(1 for r in rows if (r.get("telemetry") or {}).get("gpu_power_w"))
        ok = (len(rows) == 36 and exc == 0 and hashes == {hash_want} and power == 36)
        print(f"{'OK ' if ok else 'BAD'}  {b}-t{t}: rows={len(rows)} exc={exc} "
              f"hash={'ok' if hashes == {hash_want} else hashes} power={power}/36")
        bad |= not ok
        all_rows += rows

if bad:
    print("\nVALIDATION FAILED — do not merge. See BAD/MISSING lines above.")
    sys.exit(1)

keys = Counter((r["task_id"], r["backend"], r.get("trial_seed") or (r.get("metadata") or {}).get("trial_seed")) for r in all_rows)
dupes = [k for k, c in keys.items() if c > 1]
assert len(all_rows) == 540 and not dupes, (len(all_rows), dupes[:3])
with open("${CANON}", "w") as f:
    for r in all_rows:
        f.write(json.dumps(r) + "\n")
acc = {}
for b in ("monolithic", "agentic", "swarm"):
    sub = [r for r in all_rows if r["backend"] == b]
    acc[b] = sum(r["correct"] for r in sub) / len(sub)
print(f"\nMERGED 540 rows -> ${CANON}")
print("accuracy: " + "  ".join(f"{b}={a:.1%}" for b, a in acc.items()))
print("reference: M5 epoch-2 = mono 50.0% / agentic 57.8% / swarm 55.6%")
print("(if swarm lands far above 55.6%, re-check before celebrating — the")
print(" poisoned cell's 72.2% valid-row figure was survivorship-biased)")
print("\nNext: transfer results-HPC/ back to the Mac (manual capture zone).")
PY
}

# ---------------------------------------------------------------------------
case "$MODE" in
  run)      submit ;;
  validate) validate ;;
  *) echo "usage: $0 [run|validate]"; exit 2 ;;
esac
