# RESUME — M4 Mini, frontier-v2.1, monolithic N=5 (AMENDED config)

**PAUSED at checkpoint 2026-07-15.** Row-level resumable — rerunning the command below
tops up the remaining cells. Nothing lost.

**What this run is:** the first dataset in the study where **N actually means something**.
Under the amended config (Amendment 2026-07-15 / engineering log §9) each trial draws its
own seed at `temperature 0.6`, so N=5 samples the model's real output distribution. The
pre-amendment data ran at temp 0 with one seed shared across trials — all N trials were the
*same* deterministic computation (~98% of cells identical on all 5 trials).

- **File:** `results/m4-ollama/frontier-v2.1-m4-ollama-14b-n5.jsonl`
- **Checkpoint:** **29 / 180 rows** (math 24, multihop 5, code 0) · **0 errors**
- **config_hash:** `2bdbb6952605c7ca` (amended — temp 0.6 + `trials.seed_strategy: offset`)
- **Model:** `deepseek-r1:14b` via Ollama · **GPU power capture LIVE** (~12 W, util ~90%)
- **ETA from here:** ~11 h (math ~408 s/cell · multihop ~60 s/cell · **code 60 cells not yet
  started — the main uncertainty**, range ~7–12.5 h)

## Survives the pause/reboot (no action)
Model on disk, `.venv`, `.env` (Ollama + `LLM_TIMEOUT_S=1800`), and the 29 committed rows.

## Killed by a reboot (restart these)
The Ollama server and the trial process.

## Resume
```bash
cd /Users/ericmedlock/Documents/GitHub/MSAI-LLM-PERFORMANCE

# 1. Ollama (skip if already serving)
curl -sf http://localhost:11434/api/tags >/dev/null || \
  (OLLAMA_HOST=127.0.0.1:11434 ollama serve > /tmp/ollama_serve.log 2>&1 &)
sleep 3; ollama list | grep deepseek-r1:14b || ollama pull deepseek-r1:14b

# 2. (only if any backend_exception rows appeared) clean them so they retry —
#    resume treats ANY existing row as done, including failures.
./.venv/bin/python - <<'PY'
import json
f="results/m4-ollama/frontier-v2.1-m4-ollama-14b-n5.jsonl"
rows=[json.loads(l) for l in open(f)]
keep=[r for r in rows if r.get("error_category")!="backend_exception"]
open(f,"w").write("".join(json.dumps(r)+"\n" for r in keep)); print(f"kept {len(keep)}/{len(rows)}")
PY

# 3. resume (skips the 29 done cells)
MANIFEST=tasks/frontier_v2_1_manifest.json \
OUT=results/m4-ollama/frontier-v2.1-m4-ollama-14b-n5.jsonl TRIALS=5 \
  bash scripts/run_trials.sh local --backend monolithic
```

## On completion
1. Report **per-task variance** (how many of the 36 cells genuinely split across the 5
   trials — impossible to measure before this amendment), accuracy **with real error bars**,
   and the **power** profile.
2. Append to `docs/ENGINEERING_LOG.md`; commit the JSONL + `results/m4-ollama/host/local.json`; push.
3. **Follow-up flagged:** the v2.1 tier was calibrated at **temp 0**; early sampling data is
   already drifting (math 57% vs the 42% calibration, small n). The tier's [0.4, 0.7] band
   likely needs re-verification under sampling.

## Gotchas
- `LLM_TIMEOUT_S=1800` in `.env` is required (B6): at ~10 tok/s a full 6144-token turn
  exceeds the stock 600 s client timeout.
- Do NOT edit `config/config.yaml`, `tasks/*_manifest.json`, or `prompts/` — frozen, and
  `config.yaml` bytes are hashed into every row's `config_hash`.
