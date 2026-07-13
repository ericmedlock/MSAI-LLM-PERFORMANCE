# Runbook — UNCC Starlight HPC (frontier-v2.1)

The frontier tier is **frozen at v2.1** (`tasks/frontier_v2_1_manifest.json`, 2026-07-11;
36 items, 12/domain; code domain re-sourced for the production Ollama stack, commit
`2a276b5`). The Shadow PC trial (RTX A4500, 2026-07) already validated the CUDA/NVML
telemetry path and the Ollama provider on NVIDIA hardware — its purpose is served; no
further Shadow runs are planned. What remains is HPC compute.

## Cluster facts (Starlight — confirmed from OneIT docs, 2026-07-13)

- Login: `ssh <user>@hpc.charlotte.edu` (Duo). Scheduler: SLURM.
- Partition for all study jobs: `GPU` (the default partition is CPU-only — never omit it).
- **GPU pin: A40** (`--gres=gpu:A40:1`; nodes str-gpu[15-20], 4×A40 48GB each, 32 cores,
  ~256GB RAM). One GPU family across all cells keeps telemetry comparable; every row also
  stamps `gpu_name`/`gpu_uuid` as proof.
- Per-user limits (GPU partition): 12 active GPUs, 128 active jobs, 30-day max walltime.
- Defaults if unspecified are wrong for us (8h walltime, 2GB/task) — the job script sets
  `--time` and `--mem` explicitly.
- Storage: home `/users/$USER` 500GB (backed up); scratch `/scratch/$USER` 5TB (NOT backed
  up, purged under pressure). Model blobs go to scratch: the scripts default
  `OLLAMA_MODELS=/scratch/$USER/ollama-models` on HPC automatically.
- GPU inventory check: `sinfo -p GPU -o "%20N %6c %8m %34f %20G"`

## The two-command flow

```bash
# LOGIN NODE (has internet) — one-time per cluster: venv + deps + offline tests +
# no-root Ollama + model pull to scratch. Pin the server build for reproducibility:
OLLAMA_VERSION=v0.9.6 bash scripts/setup.sh --download    # pick the pinned release

# submit the confirmatory sweep: 3 array elements (monolithic/agentic/swarm),
# one A40 each, own Ollama server on a private port, own output file
sbatch scripts/job_frontier_a40.sbatch
```

Each job runs `setup.sh --offline` first (artifact sanity check — fails fast with a named
remedy if the login-node download step was skipped; compute nodes are assumed to have no
internet) and then `run_trials.sh hpc`, which:

1. refuses to append to an output file whose rows carry a different `model_tag`,
2. starts its own `ollama serve` on a port derived from `$SLURM_JOB_ID` (no collisions
   when jobs share a node),
3. warms the model and **aborts unless ≥90% of the weights are in VRAM** (catches the
   silent-CPU-fallback failure mode before burning walltime),
4. launches the resumable runner (requeue/timeout safe — resubmitting is always safe).

Smoke test before the real submit (prints the plan, no server, no GPU):

```bash
DRYRUN=1 bash scripts/run_trials.sh hpc
```

## Stage plan

| Stage | Command | Cells | Est. |
| --- | --- | --- | --- |
| 1. Smoke (login node) | `DRYRUN=1 bash scripts/run_trials.sh hpc` | plan only | seconds |
| 2. Confirmatory (pre-registered) | `sbatch scripts/job_frontier_a40.sbatch` | 3 backends × 36 items × N=5 | ~4–5h wall (3 GPUs) |
| 3. Scaling leg 32B (exploratory) | same script, submit-time overrides (header of the .sbatch has the exact line) | 3 × 36 × N=2 | ~½ day |
| 4. Swarm-size A/B (exploratory) | design in progress — big-M peer pool + offline subset voting | 1 GPU-evening/arm | — |

Notes: scaling legs use `--export=ALL,LLM_MODEL=...,MODEL_TAG=...,TRIALS=2,OUT_PREFIX=...`
(machine/variant config goes through the environment, never `config/config.yaml`). The 32B
Q4 (~20GB) fits the A40 — same family pin holds for every leg.

## Monitoring

```bash
squeue -u $USER                              # queue state
tail -f runs/slurm-<jobid>_<idx>.out         # live job log
wc -l results/frontier-v2.1-hpc-14b-*.jsonl  # rows vs expected (36 × N per backend)
seff <jobid>                                 # post-mortem resource efficiency
```

## After any run

Commit the results JSONL + `results/host/hpc.json`, push, then on the analysis machine
(judge stays on the laptop — it needs the served Llama-3.2-3B judge model):

```bash
./.venv/bin/python -m harness.judge
./.venv/bin/python -m harness.analyze --results "results/frontier-v2*.jsonl" \
    --output results/frontier-v2-analysis.md --charts
```

## Integrity checklist

- [ ] `git status` clean before starting (config edits change `config_hash`)
- [ ] One model per output file — `run_trials.sh` now enforces this, but don't fight it
- [ ] Frozen files are immutable: `tasks/*_manifest.json`, `prompts/`, `config/config.yaml`
- [ ] Every HPC row shows `gpu_name` = A40 (homogeneity check: it's in `telemetry`)
- [ ] Timeouts/requeues are safe — resubmit, nothing is lost

## Appendix: manual single job (no array)

```bash
#!/bin/bash
#SBATCH --job-name=frontier-manual
#SBATCH --partition=GPU
#SBATCH --gres=gpu:A40:1
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --requeue
cd $SLURM_SUBMIT_DIR
bash scripts/setup.sh --offline
bash scripts/run_trials.sh hpc          # all 3 backends sequentially in one file
```

Site unknowns still open (harmless — first login session answers them): whether compute
nodes have internet (the offline split assumes not, which covers both), whether an
account/allocation string is required at submit, and whether a `module load` is needed for
driver visibility (the GPU-residency guard catches it if so — remedy: `module load cuda`
in the job script).
