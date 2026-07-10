# Runbook — Shadow Trial + HPC Sweeps (unified setup engine)

The frontier tier is **frozen** (`tasks/frontier_v2_manifest.json`, 2026-07-09; 36 items,
12/domain, all domain aggregates in the [0.4, 0.7] band at the pinned 14B). What remains
is compute. Every machine uses the same two commands; the scripts detect the platform
(Windows+NVIDIA → `shadow`, SLURM/Linux+NVIDIA → `hpc`, macOS → `local`) and serve the
model with **Ollama** — the same provider the Azure cloud cell pins, so every trial also
rehearses that path.

```bash
git clone <repo-url> && cd MSAI-LLM-PERFORMANCE
bash scripts/setup.sh        # venv + deps + offline tests + Ollama (no root on Linux) + model pull
bash scripts/run_trials.sh   # auto-profile; or: run_trials.sh shadow|hpc|local
```

On a box with Claude Code, just say **"RUN SHADOW PC TRIALS"** (or "run setup") — the
repo ships a skill (`.claude/skills/run-trials/`) that drives the same two scripts and
knows the ground rules (never touch config/manifests/prompts; commit results + host
profile when done).

## Stage plan

| Stage | Where | Command | Backends × N | Est. |
|---|---|---|---|---|
| 1. Trial / telemetry validation | Shadow Power Pro (RTX A4500 24 GB) | `run_trials.sh shadow` | 3 × N=1 (108 runs) | ~2–3 h |
| 2. Confirmatory (pre-registered) | UNCC HPC | `run_trials.sh hpc` | 3 × N=5 (540 runs) | ~1 GPU-day |
| 3. Scaling legs (exploratory) | UNCC HPC | `MODEL=... TRIALS=2 OUT=...` | 3 × N=2 (216/model) | ~½ day each |

**Stage 1 checks** (why the Shadow trial exists): first NVIDIA environment this harness
has ever run — inspect the first few rows of `results/frontier-v2-shadow-trial-14b.jsonl`
and confirm `peak_vram_mb` / GPU-util / power fields are populated (pynvml path), rows
carry `environment=shadow` + a `results/host/shadow.json` profile, and the Ollama
provider behaves at `num_ctx=8192` (sent per-request; no manual context config).

## HPC notes

- `setup.sh` installs Ollama **without root** (standalone tarball → `~/.local`); models
  cache under `~/.ollama` (set `OLLAMA_MODELS` to scratch if home is quota'd).
- SLURM template:

```bash
#!/bin/bash
#SBATCH -J frontier-14b
#SBATCH --gres=gpu:1        # 14B Q4 ≈10 GB VRAM; 32B ≈20 GB
#SBATCH --mem=32G
#SBATCH -t 24:00:00
#SBATCH --requeue           # safe: row-level checkpointing resumes automatically

cd $SLURM_SUBMIT_DIR
bash scripts/setup.sh
bash scripts/run_trials.sh hpc
```

- Scaling legs (stage 3): same job with env overrides, e.g.
  `LLM_MODEL=deepseek-r1:32b MODEL_TAG=deepseek-r1-distill-qwen-32b TRIALS=2 OUT=results/frontier-v2-hpc-32b.jsonl bash scripts/run_trials.sh hpc`
  (machine-specific overrides go through the environment/.env, never config.yaml).
- Seeding the confirmatory job: the 180 monolithic calibration rows are valid
  confirmatory rows **only if the served artifact matches the pinned digest** —
  see `config.yaml model.digest`. When in doubt, don't seed; 6 GPU-hours is cheap
  next to a provenance question.

## After any run

Commit the results JSONL + `results/host/<env>.json`, push, then on the analysis machine:

```bash
./.venv/bin/python -m harness.judge
./.venv/bin/python -m harness.analyze --results "results/frontier-v2-*.jsonl" \
    --output results/frontier-v2-analysis.md --charts
```

## Integrity checklist

- [ ] `git status` clean before starting (config edits change `config_hash`)
- [ ] One model per output file; never mix models in one JSONL
- [ ] Frozen files are immutable: `tasks/*_manifest.json`, `prompts/`, `config/config.yaml`
- [ ] Timeouts/requeues are safe — resubmit, nothing is lost
