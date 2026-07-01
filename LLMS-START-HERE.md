# LLMS START HERE

Entry point for anyone (human or AI) picking up this repo. Last updated: 2026-07-01.

Project: ITCS 6881 Independent Study (Summer 2026) · Student: Eric Medlock · Advisor: Dr. Jinzhen Wang

## What this is

A controlled benchmark comparing three LLM execution architectures under identical
model/prompt/task/decoding settings:

- **Monolithic** — one prompt in, one response out
- **Agentic** — sequential Executor + Verifier loop (LangGraph)
- **Swarm** — parallel peers, majority vote (LangGraph)

Goal: characterize *when* each architecture wins on accuracy, latency, tokens, and
hardware footprint.

## Status: v1 frozen ✅

- Full local dataset frozen at tag **`data-freeze-2026-07-01`**: 225 runs
  (15 tasks × 3 backends × N=5), one `config_hash`, all judged, hardware-stamped.
- Model: `deepseek-r1-distill-qwen-14b` (Q4_K_M) served via **LM Studio** on an
  **Apple M5 Max (48 GB)**.
- **Headline result:** agentic 100% (verifier fixes errors, Pareto-optimal),
  monolithic 93% (cheapest), swarm 93% (dominated — peers agreed on wrong answers).
  Full report: [results/analysis.md](results/analysis.md).

## The source of truth

**[PRE_REGISTRATION.md](PRE_REGISTRATION.md)** — every pinned decision (model,
decoding, topologies, task suite, N, metrics) is frozen there. All changes after
the freeze are in its **Amendment Log**. Do not deviate without logging.

## Run it (3 phases)

```bash
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pytest -m "not integration"          # offline tests
./.venv/bin/python -m harness.run --trials 5               # 1) benchmarks -> results/<env>.jsonl
./.venv/bin/python -m harness.judge                        # 2) LLM-as-judge  -> results/judge/
./.venv/bin/python -m harness.analyze --charts             # 3) report + charts
```

See [README.md](README.md) for setup (LM Studio / provider config via `.env`, the
Azure cloud cell) and [results/README.md](results/README.md) for the data dictionary.

## Map of the repo

| Path | What |
| --- | --- |
| `PRE_REGISTRATION.md` | Frozen study design + Amendment Log (source of truth) |
| `README.md` | Setup, provider/`.env` config, run instructions, reproducibility |
| `config/config.yaml` | All pinned values (nothing pinned is hardcoded) |
| `backends/` | Shared `Backend` interface + monolithic / agentic / swarm |
| `harness/` | config, graders, telemetry, runner, judge, analysis, host profiling |
| `tasks/manifest.json` | Frozen 15-item **baseline** task suite (5 per domain) |
| `tasks/frontier_manifest.json` | Candidate **frontier** tier (architecture-favoring); see `docs/TASK_TIERS.md` |
| `prompts/` | Version-controlled system prompts (frozen after pilot) |
| `results/` | Frozen dataset, judge rows, hardware profile, report, charts |
| `scripts/` | Azure provisioning, env/hardware snapshots, backfill |
| `docs/STRETCH_GOALS.md` | v2 plan (OpenAI Swarm + CrewAI migration, ensemble swarm) |

## What's next (v2)

See [docs/STRETCH_GOALS.md](docs/STRETCH_GOALS.md): migrate swarm→OpenAI Swarm and
agentic→CrewAI (v1 stays the LangGraph baseline), add a 15-drone **ensemble swarm**
condition, and run the **Azure cloud cell** for the on-prem-vs-cloud half.
