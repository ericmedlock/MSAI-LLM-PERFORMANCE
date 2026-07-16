# HPC re-run handoff — amended-config confirmatory cell (for the Claude session driving Starlight)

**Written 2026-07-15 by the M5-side session.** Your mission: regenerate the HPC
confirmatory cell (36 tasks × 3 architectures × N=5 = 540 rows) under the
**amended config**, sharded across as many A40s as the cluster will give you, then
commit/push so the cells join. Eric is running M4 at N=1; the M5 session is running
its 540-row cell now. **N=5 everywhere except M4.**

## 1. What has been learned (context you must not re-derive)

- **The N-trials flaw (eng log §9):** all pre-2026-07-15 data ran temp 0 + one seed
  across trials → the 5 "trials" were byte-identical replays. Amendment 2026-07-15:
  `temperature: 0.6` + `trials.seed_strategy: offset` (stride 1000). N now draws real
  samples. **Old-epoch data (config hash `e33a15cdfd8a0c35`) stays valid as point
  estimates / mechanism evidence; new-epoch data carries the statistics.** Never mix
  epochs unflagged.
- **Agentic false revisions (eng log §8, Amendment 2026-07-14):** the strict
  first-line verdict parse destroys correct answers; lenient (last APPROVE/REVISE
  token) is the validated protocol. **The factory still defaults to strict — you MUST
  export `AGENTIC_VERDICT=lenient`** (see §3). The M5 new-epoch cell runs lenient.
- **Swarm is not an ensemble at 14B (wiki F2):** four independent probes (zero
  contested votes at temp 0; swarm 2.0 regression; k-voter sim; AST re-vote merging
  0/55 code ties). At the new baseline temp 0.6 peers sample by default — watch
  whether contested votes finally appear; that's a finding either way.
- **Energy economics (eng log §11, wiki F10):** M5 ≈ 1.6–1.8 tokens/joule vs your A40
  deployment's 0.12. kJ-per-correct-answer flips ranking by platform. **Your NVML
  power telemetry is load-bearing for the paper — keep it on and verify it per row.**
- **⚠️ THE A40 ANOMALY — investigate BEFORE burning GPU-hours (eng log §11.3):** the
  A40 ran at **17.5 tok/s — half the throughput of a much weaker RTX A4500** — at 83%
  reported GPU util. Suspects: ollama build/version, CPU-side bottleneck (advisor
  flagged agentic orchestration is CPU-heavy), container CPU limits, num_ctx, node
  contention. Running 540 rows on a broken deployment doubles cost and contaminates
  the epoch-2 energy table. Profile one task first; fix or document before scaling.

## 2. Check FIRST (in order, before any big submission)

1. `git pull` — you need ≥ `3f3447a`. Read eng log §8–§12 and the vault-mirrored
   claims in `results/POST_RUN_NOTE_2026-07-15_provenance_and_taxonomy.md`.
2. **Smoke row** (1 task, monolithic, TRIALS=2): confirm the row stamps
   `config_hash: 2bdbb6952605c7ca` (must equal M4/M5 new-epoch cells — if it differs,
   STOP: your config.yaml diverges), `decoding` temp 0.6, and **different trial seeds
   → different answers across the 2 trials** (per-trial independence audit).
3. Confirm `AGENTIC_VERDICT=lenient` reaches the process (`ps eww`, or check a row's
   `metadata.verdict_mode`). Env var, not config — it is NOT covered by the hash.
4. NVML telemetry: `requirements-cuda.txt` installed; honor `CUDA_VISIBLE_DEVICES`
   (the index bug is already fixed in `harness/telemetry.py` — each Slurm job samples
   ITS device); verify `gpu_power_w` non-null on the smoke row.
5. Pin to the A40s in the `GPU` partition (cell homogeneity — rows stamp
   `gpu_name`/`gpu_uuid`, keep them uniform).
6. Investigate the §11.3 throughput anomaly (one profiled task). Document what you
   find in eng log §11.3 either way.

## 3. Parallelization plan (Eric's intent, translated to this harness)

Eric's sketch: "1 GPU per agent" → mono 1 + agentic 1 + swarm 3 = 5 GPUs per
replicate, × N=5 replicates = **25 GPUs**, capped by A40 availability, chunked to run
in parallel both across and within replicates.

**Translation that keeps the science pinned:** the harness parallelizes safely at the
**row level**, not inside a row. Peers of one swarm row share their job's GPU (that
serving topology is part of the pinned deployment — same as M5/M4; putting each peer
on its own GPU would change contention characteristics mid-study and confound the
cross-platform comparison; see §5 for that as a separate experiment).

- **Shard = (backend × trial) = 3 × 5 = 15 independent jobs, up to 15 GPUs
  concurrently.** Each shard: 36 tasks, one backend, ONE trial index, own Ollama
  instance on its own A40 (unique port per job — never share one Ollama across jobs).
  Expected wall-clock: ~1.5–3 h per shard at current throughput → **the whole 540-row
  cell in ~3 h** (better if you fix the anomaly). This meets "shrink time as much as
  reasonable" with zero science change. If fewer GPUs are free, shards queue — any
  subset works, order irrelevant.
- **Missing piece you must add:** the runner has no trial-slice flag —
  `harness/runner.py` loops `trial_idx in range(1, trials+1)` internally. Add a
  `--trial <t>` (or `TRIAL_INDEX` env) that runs exactly trial *t*: seeds derive from
  `config.trial_seed(trial_idx)`, so a slice reproduces the same seeds as a full run
  — harness logistics, not a pinned-science change. Keep the resume key as-is
  (it already includes trial_idx). Add a unit test (see `tests/test_runner.py`
  for the pattern).
- **File discipline: one writer per file.** Each shard writes its own OUT
  (`results-HPC/hpc-shards/frontier-v2.1-hpc-14b-<backend>-t<t>.jsonl`), then concatenate
  into the canonical `results-HPC/frontier-v2.1-hpc-14b-n5.jsonl` after validation
  (540 rows, no dupes on (task,backend,trial), single config hash, power non-null).
  Old-epoch HPC files keep their existing names — if anything collides, follow the
  M4 rename convention (`*-DETERMINISTIC-N-temp0.jsonl` suffix on the OLD file).
- Slurm shape: a 15-element array job is the natural fit; per-element
  `CUDA_VISIBLE_DEVICES` comes from Slurm, telemetry already honors it.

## 4. Deliverables

1. 540 validated rows, amended config, lenient agentic, power telemetry on every row.
2. Eng log updates: §11.3 anomaly findings; a §13 for the sharded-run mechanics if
   you learn anything worth keeping.
3. Commit + push (data + any harness changes with tests). Watch for races: three
   machines are pushing to main today — pull --rebase before push.
4. Headline comparison vs old-epoch HPC cell (61/51/50%) once complete — flag
   anything that moves by more than a few tasks' worth.

## 5. Explicitly out of scope (unless Eric asks)

- **True parallel swarm** (each peer on its own GPU/endpoint): interesting F9-related
  demo Eric has mused about ("grab 9–12 GPUs... just a raw number"), but it changes
  the serving topology and needs multi-endpoint routing in `backends/swarm.py`. Run it
  as a separate labeled experiment AFTER the confirmatory cell, never mixed into it.
- Re-running Shadow, or any old-epoch variant cell (agentic 2.0 / swarm 2.0) — the
  temp-0.6 baseline supersedes the swarm 1.0-vs-2.0 distinction, and lenient is now
  the standard agentic mode.
