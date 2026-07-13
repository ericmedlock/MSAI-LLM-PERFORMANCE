# M5 Max — agentic + swarm N=5 runbook (run this when on the Mac)

**Why:** the M5 Max has only **monolithic** frontier-v2 data (`results/frontier-v2-calib-14b.jsonl`,
N=1–5). To complete the cross-environment architecture comparison it needs **agentic + swarm** on the
same frozen `frontier_v2_manifest.json` at **N=5**. This is item 3 of the current plan; it cannot run
from the Shadow box (different machine + LM Studio/Metal), so it is staged here.

**Prereq — the client fix must be present.** Pull `main` first so you have the
`backends/llm_client.py` fix (recover answer from the reasoning field when content is empty). On LM
Studio that field is usually inline in `content`, so the fix is mostly a no-op there — but pull anyway
to keep both environments on identical code.

```bash
cd ~/…/MSAI-LLM-PERFORMANCE
git pull

# LM Studio must be serving deepseek-r1-distill-qwen-14b (Q4_K_M) on :1234
# with context length set to 8192 (config decoding.num_ctx) — the OpenAI API
# cannot set num_ctx per request. Start Server in LM Studio's Developer tab.

bash scripts/setup.sh            # detects 'local' (Darwin); builds venv, runs offline tests
```

## Run (agentic + swarm only, N=5, fresh output file)

`run_trials.sh local` defaults to all 3 backends at N=5. Monolithic is already done, so restrict to
the two missing architectures and write to a **new** file so the calibration data is untouched:

```bash
# agentic
TRIALS=5 OUT=results/frontier-v2-local-n5-arch.jsonl \
  bash scripts/run_trials.sh local --backend agentic

# swarm  (appends to the same file; runner is idempotent/resumable)
TRIALS=5 OUT=results/frontier-v2-local-n5-arch.jsonl \
  bash scripts/run_trials.sh local --backend swarm
```

- 36 tasks × 2 backends × 5 trials = **360 runs**. Row-level checkpointed — Ctrl-C / requeue safe;
  rerun the same command to resume.
- Metal telemetry note: `peak_vram_mb`/`gpu_util`/`gpu_power` are `None` on Metal by design (no NVML);
  `peak_sys_used_mb` carries the footprint. This is expected, not the Shadow telemetry bug.

## After it finishes

1. Sanity-check no empty answers slipped through:
   `grep -c '"error_category": "format_error"'` should be low; inspect any that appear.
2. Commit `results/frontier-v2-local-n5-arch.jsonl` (+ `results/host/local.json`) and push.
3. Combined with the monolithic calibration (N=5) and the CUDA N=5 run, this gives the full
   tier × architecture × environment comparison the pre-registration (§8) calls for.
