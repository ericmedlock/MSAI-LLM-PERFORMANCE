# RESUME — M4 Mini Ollama frontier-v2 trial

**Purpose:** frontier-v2 (frozen, 36 items) @ deepseek-r1:14b via **native Ollama**
on the Apple M4 Mini (Metal, 24 GB) — adds the Apple/Metal hardware point to the
cross-machine comparison (vs Shadow/CUDA). Rows carry the canonical
`deepseek-r1-14b-distill-q4_k_m` tag so only host/accelerator differs.

**SCOPE: monolithic DONE (36, committed 6018cb2); now running agentic + swarm (72
cells).** ETA ≈ 15–18 h on this M4 (agentic ~2–3 calls/cell, swarm 3 calls/cell,
~322 s/call). Resumable — restarting tops up remaining cells. When all 3 backends are
in, the file is the complete M4 frontier-v2 cell.

## What survives the reboot (no action needed)
- `deepseek-r1:14b` model (on disk under `~/.ollama`) — persists.
- `.venv/` (Python deps) — persists.
- `.env` (Ollama config, gitignored) — persists. Should contain:
  `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434`,
  `LLM_MODEL=deepseek-r1:14b`, `LLM_TIMEOUT_S=1800`. (MODEL_TAG intentionally UNSET.)
- Trial data so far: `results/m4-ollama/frontier-v2-m4-ollama-14b.jsonl`.

## What the reboot kills (must restart)
- The **Ollama server** and the trial process.

## Restart steps (copy/paste)
```bash
cd /Users/ericmedlock/Documents/GitHub/MSAI-LLM-PERFORMANCE

# 1. start the Ollama server (background)
OLLAMA_HOST=127.0.0.1:11434 ollama serve > /tmp/ollama_serve.log 2>&1 &
sleep 3 && curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama up"

# 2. confirm the model is present (re-pull only if missing)
ollama list | grep deepseek-r1:14b || ollama pull deepseek-r1:14b

# 3. sanity: .env still points at Ollama + has the 1800s timeout
grep -E "LLM_PROVIDER|LLM_MODEL|LLM_TIMEOUT_S" .env

# 4. (only if the file has any backend_exception rows) clean them so they retry:
./.venv/bin/python - <<'PY'
import json
f="results/m4-ollama/frontier-v2-m4-ollama-14b.jsonl"
rows=[json.loads(l) for l in open(f)]
keep=[r for r in rows if r.get("error_category")!="backend_exception"]
open(f,"w").write("".join(json.dumps(r)+"\n" for r in keep))
print(f"kept {len(keep)}/{len(rows)} rows")
PY

# 5. resume the trial (agentic+swarm; monolithic already done; skips done cells)
OUT=results/m4-ollama/frontier-v2-m4-ollama-14b.jsonl TRIALS=1 \
  bash scripts/run_trials.sh local --backend agentic --backend swarm
```

## On completion
1. Summarize accuracy by domain × backend from the JSONL (`correct` field).
2. Append the result table to `docs/ENGINEERING_LOG.md` §7.
3. Commit `results/m4-ollama/frontier-v2-m4-ollama-14b.jsonl` **+**
   `results/m4-ollama/host/local.json` (hardware provenance); push.

## Gotchas
- **Timeout (B6, fixed):** the default 600 s client timeout is too short here — a
  full 6144-token reasoning turn needs ~640 s. `LLM_TIMEOUT_S=1800` in `.env` fixes
  it. If long turns error as `backend_exception`, check that this is set.
- **Resume skips any cell that already has a row** — including error rows. Always run
  step 4's cleaner if timeouts occurred, or those cells stay permanently failed.
- Do **not** edit `config/config.yaml`, `tasks/*_manifest.json`, or `prompts/` (frozen;
  hashed into `config_hash`).
- Output is isolated under `results/m4-ollama/` so the host sidecar
  (`results/m4-ollama/host/local.json`) does not clobber the frozen `results/host/`.
