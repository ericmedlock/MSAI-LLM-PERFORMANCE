#!/bin/bash
# Unified trial runner. Detects (or takes) a profile and runs the frozen
# frontier-v2 tier with profile-appropriate defaults. Fully resumable at row
# level — Ctrl-C / requeue / rerun at will.
#
#   bash scripts/run_trials.sh                 # auto-detect profile
#   bash scripts/run_trials.sh shadow          # Shadow PC trial: 3 backends, N=1 (~2-3h)
#   bash scripts/run_trials.sh hpc             # confirmatory: 3 backends, N=5
#   bash scripts/run_trials.sh local           # pinned local cell (M5 Max)
#   TRIALS=2 OUT=... bash scripts/run_trials.sh shadow      # overrides
#   bash scripts/run_trials.sh shadow --backend monolithic  # extra harness args pass through
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${1:-auto}"; shift || true
if [ "$PROFILE" = "auto" ]; then
  if [ -n "${SLURM_JOB_ID:-}" ] || command -v sbatch >/dev/null 2>&1; then PROFILE=hpc
  else case "$(uname -s)" in
    Darwin) PROFILE=local ;;
    MINGW*|MSYS*|CYGWIN*) PROFILE=shadow ;;
    Linux) PROFILE=hpc ;;
    *) PROFILE=shadow ;;
  esac; fi
  echo "[trials] auto-detected profile: $PROFILE"
fi

MANIFEST="${MANIFEST:-tasks/frontier_v2_manifest.json}"
case "$PROFILE" in
  shadow) ENVKEY=shadow; DEF_TRIALS=1; DEF_OUT="results/frontier-v2-shadow-trial-14b.jsonl" ;;
  hpc)    ENVKEY=hpc;    DEF_TRIALS=5; DEF_OUT="results/frontier-v2-hpc-14b.jsonl" ;;
  local)  ENVKEY=local;  DEF_TRIALS=5; DEF_OUT="results/frontier-v2-14b.jsonl" ;;
  *) echo "[trials] unknown profile '$PROFILE' (use shadow|hpc|local|auto)"; exit 1 ;;
esac
TRIALS="${TRIALS:-$DEF_TRIALS}"
OUT="${OUT:-$DEF_OUT}"

VPY=".venv/bin/python"; [ -x "$VPY" ] || VPY=".venv/Scripts/python.exe"
[ -x "$VPY" ] || { echo "[trials] no venv — run: bash scripts/setup.sh"; exit 1; }

# server must be up (setup.sh does this; re-assert cheaply)
if [ "$ENVKEY" != "local" ]; then
  curl -sf http://localhost:11434/api/tags >/dev/null || bash scripts/bootstrap_model_server.sh
fi

echo "[trials] profile=$PROFILE env=$ENVKEY trials=$TRIALS -> $OUT"
"$VPY" -m harness.run --manifest "$MANIFEST" --environment "$ENVKEY" \
    --trials "$TRIALS" --output "$OUT" --dry-run "$@"
echo "[trials] launching (resumable; Ctrl-C safe)"
"$VPY" -m harness.run --manifest "$MANIFEST" --environment "$ENVKEY" \
    --trials "$TRIALS" --output "$OUT" "$@"

echo "[trials] done; rows:"; wc -l "$OUT"
echo "[trials] next: commit the results JSONL + results/host/${ENVKEY}.json and push"
