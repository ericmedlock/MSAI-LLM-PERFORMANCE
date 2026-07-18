#!/bin/bash
# ============================================================================
# COMMIT + PUSH the completed HPC swarm re-run results.
#
#   bash scripts/hpc_commit_results.sh
#
# Run on the Starlight LOGIN NODE from the repo root, AFTER the re-run array
# has drained. Fully gated: it re-runs shard validation first and refuses to
# commit anything if validation fails, so a bad cell can never reach main.
# Quarantined *.POISONED-B6.* files are gitignored — history already holds
# the originals; the poison is not re-committed.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate: validating all 15 shards (refuses to commit on failure) =="
bash scripts/hpc_swarm_rerun.sh validate

echo ""
echo "== staging results-HPC/ =="
git add -A results-HPC/
git status --short -- results-HPC/ | head -30

CANON="results-HPC/frontier-v2.1-hpc-14b-n5.jsonl"
ROWS=$(wc -l < "$CANON" | tr -d ' ')

git commit -m "data(hpc): swarm shard re-run complete; canonical epoch-2 cell merged (${ROWS} rows)

B6 fix applied (LLM_TIMEOUT_S=1800 in sbatch). All 15 shards validated:
36 rows each, zero backend_exception, amended hash 2bdbb6952605c7ca,
gpu_power_w non-null on every row. Canonical merged cell: ${CANON}.
Poisoned swarm shards quarantined locally (originals preserved in git
history at the 2026-07-15 commits)."

echo "== syncing with origin (three machines share this repo) =="
git pull --rebase origin main
git push origin main

echo ""
echo "== DONE. The M5 session takes it from here (final epoch-2 analysis). =="
