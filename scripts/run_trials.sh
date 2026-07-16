#!/bin/bash
# Unified trial runner. Detects (or takes) a profile and runs the frozen
# frontier-v2.1 tier with profile-appropriate defaults. Fully resumable at row
# level — Ctrl-C / requeue / rerun at will.
#
#   bash scripts/run_trials.sh                 # auto-detect profile
#   bash scripts/run_trials.sh shadow          # Shadow PC trial: 3 backends, N=1 (~2-3h)
#   bash scripts/run_trials.sh hpc             # confirmatory: 3 backends, N=5
#   bash scripts/run_trials.sh local           # pinned local cell (M5 Max)
#   TRIALS=2 OUT=... bash scripts/run_trials.sh shadow      # overrides
#   bash scripts/run_trials.sh shadow --backend monolithic  # extra harness args pass through
#   DRYRUN=1 bash scripts/run_trials.sh hpc    # print the run plan and exit (no server needed)
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

# frontier-v2.1 is the frozen tier as of 2026-07-11 (code domain re-sourced;
# see commit 2a276b5). v2 files remain valid data for their tier version.
MANIFEST="${MANIFEST:-tasks/frontier_v2_1_manifest.json}"
case "$PROFILE" in
  shadow) ENVKEY=shadow; DEF_TRIALS=1; DEF_OUT="results/frontier-v2.1-shadow-trial-14b.jsonl" ;;
  hpc)    ENVKEY=hpc;    DEF_TRIALS=5; DEF_OUT="results-HPC/frontier-v2.1-hpc-14b.jsonl" ;;  # HPC data is isolated in results-HPC/ (see its README)
  local)  ENVKEY=local;  DEF_TRIALS=5; DEF_OUT="results/frontier-v2.1-local-14b.jsonl" ;;
  *) echo "[trials] unknown profile '$PROFILE' (use shadow|hpc|local|auto)"; exit 1 ;;
esac
TRIALS="${TRIALS:-$DEF_TRIALS}"
OUT="${OUT:-$DEF_OUT}"

VPY=".venv/bin/python"; [ -x "$VPY" ] || VPY=".venv/Scripts/python.exe"
[ -x "$VPY" ] || { echo "[trials] no venv — run: bash scripts/setup.sh"; exit 1; }

# --- HPC job isolation (no-ops everywhere else) --------------------------------------
if [ "$ENVKEY" = "hpc" ]; then
  # Model cache on scratch — must mirror the default applied by setup.sh --download.
  if [ -z "${OLLAMA_MODELS:-}" ] && [ -d "/scratch/$USER" ]; then
    export OLLAMA_MODELS="/scratch/$USER/ollama-models"
  fi
  # Inside a SLURM job: per-job port so two jobs sharing a node never collide.
  # Uses the existing LLM_BASE_URL override — config.yaml stays untouched.
  if [ -n "${SLURM_JOB_ID:-}" ] && [ -z "${LLM_BASE_URL:-}" ]; then
    PORT=$((20000 + SLURM_JOB_ID % 20000))
    export LLM_BASE_URL="http://127.0.0.1:$PORT"
    export OLLAMA_BASE="$LLM_BASE_URL"
    echo "[trials] SLURM job $SLURM_JOB_ID -> private server port $PORT"
  fi
fi

# --- guard: one model per output file, never mixed -----------------------------------
# The one unrecoverable mistake is two models' rows in one JSONL. Compare the
# existing file's last row against the tag the harness will stamp (config +
# MODEL_TAG/.env overrides, same resolution path as the runner itself).
if [ -s "$OUT" ]; then
  "$VPY" - "$OUT" <<'PY'
import json, sys
from harness.config import load_config, load_dotenv
load_dotenv()
with open(sys.argv[1], "rb") as f:
    last = f.readlines()[-1]
have = json.loads(last).get("model_tag")
want = load_config("config/config.yaml").model.resolved().tag
if have != want:
    sys.exit(f"[trials] REFUSING to run: {sys.argv[1]} holds model_tag={have!r} "
             f"but this run would stamp {want!r}. One model per file — "
             f"pick a different OUT=... for this model.")
print(f"[trials] output-file guard OK (resuming {want})")
PY
fi

# server must be up (setup.sh does this; re-assert cheaply)
BASE="${LLM_BASE_URL:-http://localhost:11434}"
if [ "$ENVKEY" != "local" ] && [ -z "${DRYRUN:-}" ]; then
  curl -sf "$BASE/api/tags" >/dev/null || bash scripts/bootstrap_model_server.sh "${LLM_MODEL:-deepseek-r1:14b}"
fi

# --- guard (hpc): model must be GPU-resident, not silently on CPU --------------------
# A missing --partition=GPU or a driver mismatch makes Ollama fall back to CPU;
# the run would "succeed" ~10x slower with empty VRAM telemetry. Warm the model
# and require >=90% of its weights in VRAM before burning walltime.
if [ "$ENVKEY" = "hpc" ] && [ -z "${DRYRUN:-}" ]; then
  echo "[trials] verifying model is GPU-resident on $BASE"
  LLM_BASE_URL="$BASE" LLM_MODEL="${LLM_MODEL:-deepseek-r1:14b}" "$VPY" - <<'PY'
import json, os, urllib.request
base, model = os.environ["LLM_BASE_URL"], os.environ["LLM_MODEL"]
req = urllib.request.Request(f"{base}/api/generate", json.dumps(
    {"model": model, "prompt": "hi", "options": {"num_predict": 1}}).encode(),
    {"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=900).read()  # cold load included
ps = json.load(urllib.request.urlopen(f"{base}/api/ps", timeout=30))
loaded = [m for m in ps.get("models", []) if model in (m.get("name"), m.get("model"))]
size = loaded[0].get("size", 0) if loaded else 0
vram = loaded[0].get("size_vram", 0) if loaded else 0
print(f"[trials] {model}: size={size/1e9:.1f}GB vram={vram/1e9:.1f}GB")
if vram <= 0 or (size and vram / size < 0.9):
    raise SystemExit("[trials] FATAL: model is not GPU-resident "
                     "(check --partition=GPU/--gres and the node's driver)")
PY
fi

echo "[trials] profile=$PROFILE env=$ENVKEY trials=$TRIALS manifest=$MANIFEST -> $OUT"
"$VPY" -m harness.run --manifest "$MANIFEST" --environment "$ENVKEY" \
    --trials "$TRIALS" --output "$OUT" --dry-run "$@"
if [ -n "${DRYRUN:-}" ]; then
  echo "[trials] DRYRUN=1 — plan printed, exiting before launch"
  exit 0
fi
echo "[trials] launching (resumable; Ctrl-C safe)"
"$VPY" -m harness.run --manifest "$MANIFEST" --environment "$ENVKEY" \
    --trials "$TRIALS" --output "$OUT" "$@"

echo "[trials] done; rows:"; wc -l "$OUT"
echo "[trials] next: commit the results JSONL + $(dirname "$OUT")/host/${ENVKEY}.json and push"
