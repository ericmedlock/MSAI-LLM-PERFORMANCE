# Results — data dictionary

Everything here is raw, committed output so all figures are replayable. The
frozen v1 dataset is tag `data-freeze-2026-07-01`.

## Files

| File | What it is |
| --- | --- |
| `local.jsonl` | **Primary dataset.** One JSON object per run (225 rows: 15 tasks × 3 backends × N=5). Self-contained — each row carries its hardware (`host_id` + `host` label) and model. |
| `judge/local.jsonl` | LLM-as-judge output, one row per run, keyed by `run_id`. Secondary quality metric; does not modify `local.jsonl`. |
| `hosts.csv` | Normalized hardware table (one row per machine, keyed by `host_id`). Join to `local.jsonl` on `host_id` for full specs. |
| `host/local.json` | Full host/hardware/model profile for the `local` environment. |
| `analysis.md` | Human-readable report (mean±std, Pareto frontiers, judge agreement, error distribution). Regenerate with `python -m harness.analyze`. |
| `charts/*.png` | Accuracy-vs-latency and accuracy-vs-tokens Pareto scatter plots. |
| `archive/` | Earlier mixed-config pilot runs, kept for provenance. **Not** part of the frozen dataset. |

## `local.jsonl` row schema (key fields)

| Field | Meaning |
| --- | --- |
| `run_id` | Unique id; join key to `judge/`. |
| `backend` | `monolithic` \| `agentic` \| `swarm`. |
| `environment` | `local` \| `cloud`. |
| `task_id`, `task_domain` | Frozen task id and domain (`gsm8k`/`humaneval`/`hotpotqa`). |
| `trial_idx` | 1..N. |
| `correct` | Primary binary auto-grade result. |
| `error_category` | Gupta-taxonomy category on failure (else null). |
| `latency_s`, `tokens_in`, `tokens_out`, `total_tokens`, `tokens_per_s` | Primary cost metrics. |
| `action_count` | LLM calls / agent turns (1 mono, ≤2·loops agentic, =num_agents swarm). |
| `model_tag` | Canonical (provider-independent) model id. |
| `provider`, `provider_model_id` | What actually served the row (e.g. `openai` / `deepseek-r1-distill-qwen-14b`). |
| `host_id`, `host` | Hardware key + compact label (`Apple M5 Max \| 48GB unified \| metal`). Join `host_id` → `hosts.csv`. |
| `config_hash` | Hash of `config.yaml` that produced the row (provenance). |
| `telemetry` | `{runtime, peak_ram_mb (harness proc), peak_sys_used_mb (whole system), avg_cpu_pct, peak_vram_mb, avg_gpu_util_pct, gpu_power_w}`. VRAM/util/power are CUDA-only; null on Metal. |
| `metadata` | Backend-specific (agentic: loops/approved; swarm: vote_counts, peer_latencies, parallel_speedup). |
| `raw_trace` | Full interaction transcript (JSON string). |

## `judge/local.jsonl` row schema

`run_id`, `task_id`, `backend`, `environment`, `judge_model`, `judge_score`
(0..`judge_max_score`), `judge_correct` (independent verdict), `judge_reason`,
`parse_ok`.

## Reproduce

```bash
python -m harness.run --trials 5     # regenerate local.jsonl
python -m harness.judge              # regenerate judge/local.jsonl
python -m harness.analyze --charts   # regenerate analysis.md + charts
```
