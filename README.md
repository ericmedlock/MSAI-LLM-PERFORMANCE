# LLM Execution Architecture Benchmark

Controlled comparison of **monolithic**, **agentic**, and **swarm** LLM
execution architectures across an **on-prem (Apple M5 Max / Metal)** and a
**cloud (Azure GPU VM / CUDA)** environment.

> **Source of truth:** [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md). All
> pinned decisions (model, decoding, topologies, task suite, N, metrics) are
> frozen there. This code implements it; it does not re-decide anything. Any
> change goes in the pre-registration Amendment Log.

One interface, three engines, two environments, identical tasks. The only
things that vary across the six cells (`L-M L-A L-S C-M C-A C-S`) are the
**architecture** and the **environment** — model, quantization, prompts,
task inputs, temperature (`0.0`), context window, and max-tokens are held
constant and live in [`config/config.yaml`](config/config.yaml), never in code.

## Layout

```text
config/config.yaml        # all pinned values (nothing pinned is hardcoded)
prompts/                  # version-controlled system prompts, frozen after pilot
  monolithic/ agentic/ swarm/
tasks/manifest.json       # 9 frozen items (3 GSM8K / 3 HumanEval / 3 HotpotQA)
backends/
  base.py                 # Backend ABC + BackendResult + Task (the shared contract)
  llm_client.py           # LLMClient protocol + pinned OllamaClient
  monolithic.py           # single call
  agentic.py              # Executor+Verifier loop, max 2 (LangGraph, sequential)
  swarm.py                # 3 peers in parallel, no controller, majority vote (LangGraph)
  factory.py              # build backends/client from config
harness/
  config.py telemetry.py graders.py task_loader.py results.py runner.py run.py
results/                  # per-run JSONL telemetry (committed — figures are replayable)
scripts/                  # env snapshot + Azure provisioning
tests/                    # offline pytest suite (no model, no GPU, no network)
```

## Model server (provider) configuration

The client layer is provider-agnostic. Each environment in
[`config/config.yaml`](config/config.yaml) selects a `provider`:

| provider | server | endpoint style | telemetry |
| --- | --- | --- | --- |
| `openai` | **LM Studio** (current local), vLLM, llama.cpp | `POST {base_url}/chat/completions`, `base_url` ends in `/v1` | Metal (no GPU power) |
| `ollama` | Ollama (Azure cloud cell) | `POST {base_url}/api/chat` | CUDA (`pynvml`) |

Endpoints, provider, model id, and API key are **machine-specific**, so they
can be overridden per box via a `.env` file (gitignored) without touching the
committed config — copy [`.env.example`](.env.example) to `.env` and edit.
Pinned scientific parameters (temperature, N, topologies, …) live only in
config.yaml and are **not** overridable via `.env`. Every row records both the
canonical `model_tag` and the `provider`/`provider_model_id` that actually
served it.

```bash
# Overrides (optional). Defaults already target LM Studio on this machine.
cp .env.example .env
#   LLM_PROVIDER=openai
#   LLM_BASE_URL=http://localhost:1234/v1
#   LLM_MODEL=deepseek-r1-distill-qwen-14b
```

## Quick start (Apple M5 Max — local cell, LM Studio)

```bash
# 1. Python env (note: a broken `python3` alias may exist; use an explicit interpreter)
python3.13 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# 2. Offline smoke test — verifies structure without touching a model
./.venv/bin/python -m pytest -m "not integration" -q

# 3. In LM Studio: load `deepseek-r1-distill-qwen-14b` (Q4_K_M) and start the
#    local server (Developer tab → Start Server, default port 1234). Set the
#    model's context length to match config `decoding.num_ctx` (8192) — the
#    OpenAI API cannot set it per-request.

# 4. Live check against LM Studio (skips automatically if the server is down)
./.venv/bin/python -m pytest -m integration -rs

# 5. Record an environment snapshot (commit alongside results)
./.venv/bin/python scripts/env_snapshot.py > results/env_local_$(date +%Y%m%d).json
```

## Run a pilot (1–2 tasks, local)

`config/config.yaml` has `active_environment: local`, so these hit your local
Ollama on the M5 Max. Preview the plan first, then run:

```bash
# Preview only — no model calls
./.venv/bin/python -m harness.run --task-id gsm8k-001 --dry-run

# Pilot: ONE task, all three backends, N=5  (15 runs)
./.venv/bin/python -m harness.run --task-id gsm8k-001

# Pilot: TWO tasks, all three backends, N=5  (30 runs)
./.venv/bin/python -m harness.run --task-id gsm8k-001 --task-id humaneval-001

# One backend only, fewer trials (fast sanity check)
./.venv/bin/python -m harness.run --task-id gsm8k-001 --backend monolithic --trials 2
```

Output lands in `results/local.jsonl`, **one row per run**. The runner is
**idempotent/resumable**: re-running the same command tops up only missing
rows, so a crash mid-run loses nothing. Monitor the GPU in another terminal
with a macOS tool such as `sudo powermetrics --samplers gpu_power` or
[`mactop`](https://github.com/context-labs/mactop).

## Scoring: auto-grade (primary) + LLM-as-judge (secondary)

Two phases, run in order — **all benchmarks first, then judge as
post-processing** (one GPU can't hold the backend and judge models at once,
and keeping them separate keeps raw run data immutable):

```bash
# Phase 1 — run benchmarks (writes results/<env>.jsonl, binary auto-graded)
./.venv/bin/python -m harness.run --task-id gsm8k-004 --trials 5

# Phase 2 — judge the recorded answers (writes results/judge/<env>.jsonl)
./.venv/bin/python -m harness.judge          # uses Gemma; see config `judge:`

# Phase 3 — analyze (joins judge rows in automatically)
./.venv/bin/python -m harness.analyze --charts
```

- **Primary metric stays the binary auto-grader** (exact numeric / unit-test /
  normalized-string). The judge is a **secondary** quality score (0–4) plus an
  independent correctness opinion, and an *agreement-with-auto-grader* rate.
- The judge model is a **different family** (Gemma) from the Qwen-based backend
  to avoid a model rewarding its own family. Override with `JUDGE_MODEL` etc.
- Judge rows live in `results/judge/` keyed by `run_id`; the raw run rows are
  never modified. Both phases are idempotent/resumable.

## Cloud cell (Azure GPU VM)

Provisioned from committed scripts so the cloud environment is reproducible.
**Request NC-series GPU quota early** — on student subscriptions it is often
zero by default and approval can take a day.

```bash
az login
RESOURCE_GROUP=llm-bench REGION=eastus VM_SIZE=Standard_NC4as_T4_v3 \
  bash scripts/provision_azure.sh create
# then, as printed, run the remote setup (installs driver + Ollama + repo + model):
ssh azureuser@<vm-ip> 'bash -s' < scripts/setup_remote.sh
```

The remote setup flips `active_environment: cloud` on the VM and runs the
harness there, where the NVIDIA GPU is local to the process so `pynvml`
captures VRAM / utilization / power. Generate the cloud cell with the same
commands as above (they read `cloud` from config). Copy `results/cloud.jsonl`
back and commit it. **Deallocate when idle** to stop GPU billing:

```bash
bash scripts/provision_azure.sh deallocate
```

## Testing

```bash
./.venv/bin/python -m pytest --cov --cov-report=term-missing
```

The suite is fully **offline** — backends run against a scripted
`FakeLLMClient`, so the three architectures, the graders, resume/idempotency,
and swarm parallelism are all verified without a model or GPU. Uncovered
lines are the live `OllamaClient` and CUDA/NVML telemetry paths, which require
the respective hardware.

> **On Playwright:** this project has no browser/web UI, so Playwright (a
> browser-automation tool) does not apply — pytest is the correct end-to-end
> tool here. If a results dashboard is added later, Playwright E2E tests
> belong with it.

## Reproducibility invariants (enforced by config + tests)

- Model tag/digest, quantization, temperature `0.0`, context, max-tokens,
  seed, and N live in `config/config.yaml`; a `config_hash` is stamped on
  every row.
- Prompts are files under `prompts/`, frozen after the pilot.
- Agentic/swarm use role-specific prompts that **differ** from monolithic —
  documented, not hidden.
- Raw per-run telemetry is committed so all figures are replayable.

## Swarm independent-sample seeding (resolved → Amendment Log 2026-07-01)

The pre-registration (§2) treats the swarm as aggregating **independent
samples** by majority vote. Under the pinned `temperature=0.0`, a single
shared seed would make all three peers deterministically identical and the
vote degenerate — voiding that premise. Peers therefore draw with
`seed = base_seed + peer_index`, pinned in config as
`architectures.swarm.peer_seed_strategy: offset` (set to `same` to restore a
shared seed). This is recorded in the `PRE_REGISTRATION.md` Amendment Log;
raise with the advisor whether `temp>0` with a shared seed is preferred as
the diversity source instead.
