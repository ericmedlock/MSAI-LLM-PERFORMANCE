# HPC Runbook — Frontier-v2 Sweeps

The frontier tier is **frozen** (`tasks/frontier_v2_manifest.json`, 2026-07-09; 36 items,
12/domain, all domain aggregates in the [0.4, 0.7] band at the pinned 14B). What remains
is compute, not design — sized at roughly 2–3 days of M5-Max-equivalent GPU time, which
is why it runs on HPC instead of the laptop.

## The three jobs

| # | Purpose | Model | Backends | N | Est. runs | Output |
|---|---|---|---|---|---|---|
| 1 | **Confirmatory** (pre-registered) | `deepseek-r1-14b-distill-q4_k_m` | monolithic, agentic, swarm | **5** | 540* | `results/frontier-v2-14b.jsonl` |
| 2 | Exploratory scaling | `deepseek-r1-distill-qwen-32b` (Q4_K_M) | all three | 2 | 216 | `results/frontier-v2-32b.jsonl` |
| 3 | Exploratory scaling | `qwen3.6-35b-a3b` (Q4_K_M) | all three | 2 | 216 | `results/frontier-v2-qwen35b.jsonl` |

\* Job 1's 180 monolithic rows can be seeded from the local calibration file — see below.

Job 1 is the school-critical dataset (tier × architecture, pre-registered N=5).
Jobs 2–3 are exploratory (N=2 is fine under near-deterministic decoding; note it in the paper).

## One-time setup on the cluster

```bash
git clone <repo-url> && cd MSAI-LLM-PERFORMANCE
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pytest -m "not integration" -q   # offline suite; should pass
# Stage model GGUFs into a scratch dir. For the pinned 14B verify provenance:
shasum -a 256 DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf
#   must equal 4b90205bacb6938e72196dbb84cd2a79987b2f93efc270496832963e8d0f56af
#   (the digest pinned in config/config.yaml)
```

A model server is needed per job; the script defaults to **llama.cpp's `llama-server`**
(build with CUDA: `cmake -DGGML_CUDA=ON`). Any OpenAI-compatible server works — override
`SERVER_CMD`.

## Seeding job 1 with the calibration rows (saves ~6 GPU-hours)

The 180 monolithic rows from calibration are valid confirmatory rows (same model, same
config, same items). Copy them in before the run; the runner tops up only what's missing:

```bash
cp results/frontier-v2-calib-14b.jsonl results/frontier-v2-14b.jsonl
# then job 1 only executes the 360 agentic+swarm rows
```

Caveat: keep this seeding **only if** the HPC job serves the *same pinned artifact*
(digest above) — rows record `model_tag`/`config_hash`, and mixing artifacts would show.

## SLURM template

```bash
#!/bin/bash
#SBATCH -J frontier-14b
#SBATCH --gres=gpu:1          # 14B Q4 needs ~10 GB VRAM; 32B needs ~20 GB
#SBATCH --mem=32G
#SBATCH -t 24:00:00           # requeue-safe: the runner resumes at row level
#SBATCH --requeue

module load cuda  # site-specific
MODEL_GGUF=$SCRATCH/models/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf \
MODEL_TAG=deepseek-r1-14b-distill-q4_k_m \
OUT=results/frontier-v2-14b.jsonl TRIALS=5 \
bash scripts/run_frontier_hpc.sh
```

For jobs 2–3 change `MODEL_GGUF`, `MODEL_TAG`, `OUT`, and add `TRIALS=2`. Run jobs on
separate nodes/GPUs freely — they write separate files.

## After the runs

Copy the three JSONL files back into `results/` on the main machine and commit them
(raw telemetry is always committed). Then:

```bash
# judge pass (Llama-3.2-3B; different family than backbone) + analysis
./.venv/bin/python -m harness.judge
./.venv/bin/python -m harness.analyze --results "results/frontier-v2-*.jsonl" \
    --output results/frontier-v2-analysis.md --charts
```

## Integrity checklist

- [ ] GGUF digest matches config (14B job)
- [ ] `git status` clean before starting (config edits change `config_hash`)
- [ ] One model per job; never point two jobs at one output file from different models
- [ ] Timeouts/requeues are safe — just resubmit, nothing is lost
