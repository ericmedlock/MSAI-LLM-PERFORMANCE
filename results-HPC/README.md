# results-HPC/ — isolated capture zone for all Starlight/HPC data

**Why this exists (2026-07-16):** GitHub is not reachable from the HPC, so HPC result
files are transferred manually (scp/rsync). This directory is the single landing zone
for everything HPC-produced, so a manual copy can NEVER overwrite local (M5), M4, or
Shadow data living in `results/`.

## Rules

1. **Everything from the HPC lands here** — canonical cells, shards, smoke tests,
   host snapshots. Nothing HPC-related is written to `results/` anymore.
2. The harness does this automatically: `scripts/run_trials.sh hpc` and
   `scripts/job_frontier_a40.sbatch` default their OUT here, and the runner writes
   `host/<env>.json` + `hosts.csv` **next to OUT** (`harness/runner.py`), so host
   sidecars are isolated too.
3. When copying manually from Starlight: copy into this directory (or a subdirectory),
   never into `results/`. Any filename collision inside here is HPC-vs-HPC and
   therefore visible/intentional.
4. Analysis note: `harness/analyze.py`'s default glob is `results/*.jsonl` — pass
   explicit paths/globs (e.g. `results-HPC/*.jsonl`) to include HPC cells.

## Layout

- `frontier-v2.1-hpc-14b-n5.jsonl` — canonical merged new-epoch cell (after shard
  validation; see `docs/HPC_RERUN_HANDOFF.md`)
- `hpc-shards/` — per-(backend × trial) shard outputs from the 15-way A40 array
- `_smoke/` — preflight/smoke rows (never analysis data)
- `host/`, `hosts.csv` — auto-written host provenance for runs launched with OUT here

## Historical note

Old-epoch HPC cells (`frontier-v2.1-hpc-14b-{monolithic,agentic,swarm}.jsonl`,
completed 2026-07-14, deterministic-N era) remain in `results/` where the wiki,
engineering log, and analysis defaults reference them. Everything from 2026-07-16
onward lands here.
