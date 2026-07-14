# RESUME — M4 Mini Ollama frontier-v2.1 cell

**Purpose:** frontier-**v2.1** (frozen, 36 items) @ deepseek-r1:14b via native Ollama on
the Apple M4 Mini (Metal, 24 GB). Rows carry the canonical `deepseek-r1-14b-distill-q4_k_m`
tag so only host/accelerator differs from Shadow/HPC.

**Why v2.1 (not v2):** the study re-sourced the CODE domain — v2's code drifted below band
on the Ollama stack (35%). Math + multihop task_ids are identical in v2 and v2.1, so the
M4 monolithic math+multihop rows were kept; only code was redone.

**File:** `results/m4-ollama/frontier-v2.1-m4-ollama-14b.jsonl` (renamed from the v2 file;
the old `frontier-v2-m4-ollama-14b.jsonl` was filtered to v2.1-valid rows and removed —
that deletion is staged in git, commit it with the new file).

**Checkpoint:** 26/108 valid rows kept (math mono 12, multihop mono 12, math swarm 2).
Remaining this run = **12 code monolithic + 34 swarm = 46 cells**, ETA ≈ 5–6 h
(swarm ~300–500 s/cell; code mono can be long). Resumable — restarting tops up.

## Survives reboot (no action): model on disk, .venv, .env (Ollama + LLM_TIMEOUT_S=1800).
## Killed by reboot: Ollama server + trial process.

## Restart steps
```bash
cd /Users/ericmedlock/Documents/GitHub/MSAI-LLM-PERFORMANCE
OLLAMA_HOST=127.0.0.1:11434 ollama serve > /tmp/ollama_serve.log 2>&1 &   # 1. server
sleep 3 && curl -sf http://localhost:11434/api/tags >/dev/null && echo up
ollama list | grep deepseek-r1:14b || ollama pull deepseek-r1:14b          # 2. model

# 3. (only if any backend_exception rows) clean them so they retry:
./.venv/bin/python - <<'PY'
import json
f="results/m4-ollama/frontier-v2.1-m4-ollama-14b.jsonl"
rows=[json.loads(l) for l in open(f)]
keep=[r for r in rows if r.get("error_category")!="backend_exception"]
open(f,"w").write("".join(json.dumps(r)+"\n" for r in keep)); print(f"kept {len(keep)}/{len(rows)}")
PY

# 4. resume (monolithic code + swarm on v2.1; skips done cells)
MANIFEST=tasks/frontier_v2_1_manifest.json \
OUT=results/m4-ollama/frontier-v2.1-m4-ollama-14b.jsonl TRIALS=1 \
  bash scripts/run_trials.sh local --backend monolithic --backend swarm
```

## On completion
1. Summarize accuracy by domain × backend; compare to Shadow/HPC v2.1.
2. Append to `docs/ENGINEERING_LOG.md` §7 (note: math+multihop mono rows predate the
   `fix(client): recover answer from Ollama 'thinking' field` — a minor cross-version
   caveat; re-run those 24 if strict single-client consistency is wanted).
3. `git add` the renamed file + `results/m4-ollama/host/local.json`; commit; push.

## Gotchas
- Timeout: `LLM_TIMEOUT_S=1800` in `.env` (B6) — needed at ~10 tok/s.
- Resume skips any cell with a row (incl. errors) — always run the cleaner if timeouts hit.
- Do NOT edit `config/config.yaml`, `tasks/*_manifest.json`, or `prompts/` (frozen).
