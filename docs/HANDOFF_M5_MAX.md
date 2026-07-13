# Session handoff → M5 Max (read this file and execute)

**You are a fresh Claude Code session on an Apple M5 Max laptop, in the `MSAI-LLM-PERFORMANCE`
repo.** This file is a context handoff from a prior session on a Shadow PC (RTX A4500 / CUDA).
Read it top to bottom, then do the task in **§Your task**. When in doubt, the committed docs and
`PRE_REGISTRATION.md` are the source of truth.

## 0. Do this first

```bash
git pull        # main has the Shadow session's fixes + runbooks you need
```

## 1. What this project is

Controlled benchmark of three LLM execution architectures — **monolithic vs agentic vs swarm** —
across environments (Apple Metal / NVIDIA CUDA), on a single pinned model:
**DeepSeek-R1-Distill-Qwen-14B, Q4_K_M**. Model, decoding (temperature 0.0), prompts, tasks, N,
and topologies are frozen in `config/config.yaml` + `tasks/` + `prompts/`; the config's bytes are
hashed into every result row. One interface, three engines, multiple environments, identical tasks.

## 2. What just happened on the Shadow PC (context, already committed)

- Ran the frozen **frontier-v2** trial (36 tasks × 3 architectures, **N=1**) — the harness's first
  NVIDIA/CUDA validation.
- **Fixed a null-GPU-telemetry bug:** `setup.sh` wasn't installing `requirements-cuda.txt`
  (`pynvml`/`nvidia-ml-py`), so CUDA VRAM/util/power came back null. Fixed; telemetry validated on
  all 108 rows.
- **Fixed an agentic "empty answer / `format_error`" bug:** Ollama returns a reasoning model's
  chain-of-thought in a separate `message.thinking` field; when generation hits `num_predict`
  mid-reasoning, `content` is empty and the final answer was lost. Fix in
  `backends/llm_client.py` falls back to `thinking` when `content` is empty. **Parsing-only — NOT
  a pre-registration amendment.** On LM Studio (this machine) it's mostly a no-op (LM Studio inlines
  reasoning), but you already pulled it — keep both environments on identical code.
- Decided **not** to run N=5 on Shadow (out-of-scope per pre-reg; redundant with the HPC cell).

## 3. Your task

Run **agentic + swarm at N=5** on the frozen `frontier_v2_manifest.json`. The M5 Max currently has
**monolithic-only** frontier-v2 data (`results/frontier-v2-calib-14b.jsonl`, N=5); this fills in the
other two architectures to complete the on-prem cell.

**Follow `docs/M5_MAX_N5_RUNBOOK.md` exactly.** In short:

```bash
# Prereq: LM Studio serving deepseek-r1-distill-qwen-14b (Q4_K_M) on :1234,
#         context length set to 8192 (= config decoding.num_ctx).
bash scripts/setup.sh            # detects 'local' (Darwin/Metal)

TRIALS=5 OUT=results/frontier-v2-local-n5-arch.jsonl \
  bash scripts/run_trials.sh local --backend agentic
TRIALS=5 OUT=results/frontier-v2-local-n5-arch.jsonl \
  bash scripts/run_trials.sh local --backend swarm
```

36 tasks × 2 backends × 5 trials = **360 runs**, row-level checkpointed (resumable — rerun to
continue). Write to the **fresh** file above so the monolithic calibration data is untouched.

## 4. Ground rules (do not violate)

- **Never edit** `config/config.yaml`, `tasks/*_manifest.json`, or `prompts/` — frozen; bytes are
  hashed into every row. Machine-specific endpoint/model overrides go in **`.env` only**
  (see `.env.example`).
- **Metal telemetry** (`peak_vram_mb`/`avg_gpu_util_pct`/`gpu_power_w`) is `None` by design on Apple
  Silicon (no NVML). Expected, not a bug; `peak_sys_used_mb` carries the footprint.
- **Determinism caveat:** at temp 0.0 + fixed seed, per-item results are near-binary (5/5 or 0/5) —
  only serving nondeterminism gives intermediate rates; swarm's diversity comes from its per-peer
  seed offsets. So N=5 mainly characterizes variance + protocol compliance, not sampling spread.
- **Checkpointing:** every finished run is written immediately; Ctrl-C / rerun is always safe.

## 5. When the run finishes

1. Sanity-check no empty answers slipped through:
   `grep -c '"error_category": "format_error"' results/frontier-v2-local-n5-arch.jsonl` (should be
   low; inspect any that appear).
2. Summarize accuracy by domain × backend.
3. Commit `results/frontier-v2-local-n5-arch.jsonl` + `results/host/local.json`, then push.

## 6. Read for depth (all committed on `main`)

- `docs/M5_MAX_N5_RUNBOOK.md` — the exact commands for this task
- `docs/SHADOW_TRIAL_LOG.md` — full engineering log + both bug fixes
- `docs/SHADOW_VS_M5_COMPARISON.md` — A4500 vs M5 Max analysis (M5 is monolithic-only on frontier-v2)
- `results/POST_RUN_NOTE_agentic_empty_answer.md` — the agentic bug write-up (RESOLVED)
- `PRE_REGISTRATION.md` — pinned decisions + Amendment Log (source of truth)

## 7. Bigger picture (remaining confirmatory matrix)

- **HPC** — N=5, all 3 architectures (`run_trials.sh hpc`) — primary CUDA confirmatory data.
- **Azure** — N=5 cloud cell — `docs/AZURE_CLOUD_CELL_RUNBOOK.md` (staged; blocked on GPU quota).
- **M5 Max (this machine)** — agentic + swarm N=5 — **your task**, completes the on-prem cell.

Start by pulling, reading `docs/M5_MAX_N5_RUNBOOK.md`, and confirming LM Studio is up on :1234.
