---
name: run-trials
description: Set up this machine and run benchmark trials (Shadow PC, HPC, local, or any box). Use when the user says "run setup", "RUN SHADOW PC TRIALS", "run HPC trials", "run trials", or wants this repo running on a new machine.
---

# Run Trials (any machine)

This repo is self-bootstrapping. Two commands do everything; both are idempotent
and resumable.

## 1. Setup (installs venv + deps, runs offline tests, installs/starts Ollama, pulls the pinned model)

```bash
bash scripts/setup.sh
```

- Detects the platform automatically (Windows+NVIDIA → `shadow`, SLURM/Linux+NVIDIA → `hpc`, macOS → `local`).
- On Windows it installs Ollama via winget; on Linux it uses a **no-root** standalone
  tarball into `~/.local` (HPC-safe); Ollama is not pip-installable, so this script is
  the "self-contained" path.
- Requires Python 3.11+ and Git Bash (Windows). If `winget`/Python are missing,
  install those first and re-run — the script says exactly what it's missing.
- Success looks like: offline tests pass (currently 112), `ollama` healthy,
  model pulled, "[setup] DONE".

## 2. Run trials

```bash
bash scripts/run_trials.sh            # auto-detected profile
bash scripts/run_trials.sh shadow     # Shadow PC: 3 backends, N=1 (~2-3 h on an A4500)
bash scripts/run_trials.sh hpc        # confirmatory: 3 backends, N=5
```

- Runs the **frozen** frontier-v2 tier (`tasks/frontier_v2_manifest.json` — 36 items;
  never edit it, it is immutable by pre-registration).
- Row-level checkpointing: Ctrl-C anytime; rerunning the same command resumes.
- Overrides: `TRIALS=2`, `OUT=path.jsonl`, `MANIFEST=...` env vars; extra harness
  flags pass through (e.g. `--backend monolithic`).

## 3. When the run finishes (or the user stops it)

1. Summarize accuracy by domain and backend from the output JSONL (`correct` field).
2. Commit the results: the output JSONL under `results/` **plus**
   `results/host/<env>.json` (hardware provenance) — raw telemetry is always committed.
3. Push, so other machines can pull the data.

## Ground rules for the agent

- Do NOT edit `config/config.yaml` (its bytes are hashed into every row's
  `config_hash`), `tasks/*_manifest.json` (frozen), or `prompts/` (frozen).
- Machine-specific endpoint/model overrides belong in `.env` (see `.env.example`),
  never in config.
- The Shadow trial's purpose: validate the Ollama provider path and the CUDA/NVML
  telemetry fields (first NVIDIA environment for this harness) ahead of HPC/Azure.
  If `peak_vram_mb` / GPU-util fields are empty in the first few rows, stop and
  investigate `harness/telemetry.py` + `pynvml` before burning hours.
- Full HPC details: `docs/HPC_RUNBOOK.md`.
