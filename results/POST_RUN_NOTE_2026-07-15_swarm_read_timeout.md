# Post-run note — swarm `backend_exception` read-timeout (HPC A40 N=5, job 26318397)

**Raised:** 2026-07-16, on review of the frontier-v2.1 15-way A40 sharded array.
**Run:** SLURM job **26318397**, array `0-14`, ran 2026-07-15 17:45 → 22:51 UTC.
**Data:** `results-HPC/hpc-shards/frontier-v2.1-hpc-14b-{monolithic,agentic,swarm}-t{1..5}.jsonl`
**Config:** `config_hash = 2bdbb6952605c7ca`, `deepseek-r1-14b-distill-q4_k_m`, NVIDIA A40, Ollama.
**Status:** 🔴 **OPEN — the swarm cell is unusable and must be re-run.** Monolithic and agentic
are complete, clean, and unaffected.

> **TL;DR.** The sharded sbatch never exported `LLM_TIMEOUT_S`, so all 15 shards ran at the
> 600 s client default. Swarm alone blows that budget — its peers fire concurrently into an
> Ollama pinned to `OLLAMA_NUM_PARALLEL=1`, so a queued peer burns its read-timeout budget
> *waiting its turn*. 65/180 swarm rows (36%) died as `backend_exception` with empty answers,
> which score `correct=False` and push swarm's accuracy from ~72% down to 46.1% — turning the
> best architecture into the apparent worst. This is **bug B6** (ENGINEERING_LOG.md:151),
> already root-caused and fixed on the M4; the fix was simply never carried into this sbatch.

## Grid integrity (everything except the timeouts is sound)

All 15 shards completed and wrote exactly 36 rows each, 540 total. No jobs left in queue.

| check | result |
|---|---|
| rows | 540 (15 shards × 36) |
| `config_hash` | single value `2bdbb6952605c7ca` |
| distinct `task_id` | 36 |
| `(backend, trial_idx)` cells | 15, exactly 36 rows each |
| trial seeds | `1042, 2042, 3042, 4042, 5042` per backend — distinct, non-null, `offset` |
| `telemetry.gpu_name` | `NVIDIA A40` on every row |
| `telemetry.gpu_power_w` | non-null on every row |
| duplicate `(backend, trial, task)` | none |

## Symptom

`error_category` by backend:

| backend | backend_exception | reasoning_error | timeout | format_error | tool_error | clean |
|---|---|---|---|---|---|---|
| monolithic | **0** | 87 | 3 | 2 | 0 | 88 |
| agentic | **0** | 80 | 2 | 1 | 1 | 96 |
| swarm | **65** | 31 | 0 | 0 | 1 | 83 |

All 65 failures are one exception, verbatim:

```
ReadTimeout(ReadTimeoutError("HTTPConnectionPool(host='127.0.0.1', port=38794):
Read timed out. (read timeout=600.0)"))
```

Failing rows carry `answer=''`, `latency_s=0.0`, `tokens_out=0`, `tokens_per_s=None`.

They are **systematic, not flaky** — spread evenly across trials (13/14/15/11/12 for t1–t5),
and 9 tasks fail in all 5 trials (`fx2-mathA-002/005/007/009/010/011/012`, `fx21-code-002`,
`fx21-code-006`). 15 of 36 tasks are hit at least once.

## Root cause

`backends/factory.py:71` reads the per-request read timeout from the environment:

```python
timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "600"))
```

`scripts/job_frontier_a40_n5_sharded.sbatch:46-48` exports `AGENTIC_VERDICT`, `TRIAL_INDEX`,
and `TRIALS` — but **not** `LLM_TIMEOUT_S`. There is no `.env` on the HPC box setting it
either, so every shard silently took the 600 s default. (The M4 has `LLM_TIMEOUT_S=1800` in
its `.env`, per `results/m4-ollama/RESUME_NOTE.md:52` — which is why the M4 cell ran clean.)

**Why swarm alone.** Monolithic and agentic issue one request at a time, so their read
timeout covers generation only. Swarm's peers fan out from START concurrently by design,
but the pinned deployment serves them **strictly sequentially** (`OLLAMA_NUM_PARALLEL=1`,
`scripts/bootstrap_model_server.sh:73`). Every peer's read-timeout clock starts at once;
only one generates at a time. A queued peer therefore spends most of its 600 s budget
waiting for the GPU, and the last peer in line can time out before it emits a single token.

The `peer_latencies_s` staircase on a surviving row shows the serialization directly —
this is queue position, not work:

```
peer_latencies_s = [111.1, 185.6, 256.6]     wall_s = 256.6
```

**The smoking gun:** the slowest *successful* swarm row landed at **595.05 s**, immediately
below the 600 s wall, with 8 more above 550 s. The distribution is truncated exactly at the
ceiling — everything past it was cut.

## Impact on the finding

Timed-out rows carry `answer=''` and score `correct=False`, so they enter the accuracy
denominator as wrong answers:

| backend | as-scored (all 180) | valid rows only | dropped |
|---|---|---|---|
| monolithic | 48.9% (88/180) | 48.9% (88/180) | 0 |
| agentic | 53.3% (96/180) | 53.3% (96/180) | 0 |
| swarm | **46.1%** (83/180) | **72.2%** (83/115) | 65 |

As-scored, swarm is the worst architecture. On rows that actually ran, it is the best by
~19 points. **The headline conclusion inverts on an infrastructure artifact.**

⚠️ **Neither number is publishable.** 46.1% is contaminated by infrastructure failure.
72.2% is contaminated by survivorship — timeouts select for long generations, i.e. hard
tasks, and the failures are domain-skewed (math 47/60, code 18/60, **multihop 0/60**), so
the surviving 115 rows are an easy-biased subset. The cell must be re-run, not repaired
analytically.

## Fix / re-run plan

1. Add to `scripts/job_frontier_a40_n5_sharded.sbatch`, beside the existing exports:
   ```bash
   export LLM_TIMEOUT_S=1800   # B6: 600 s default times out queued swarm peers (OLLAMA_NUM_PARALLEL=1)
   ```
   1800 s matches the M4 and clears the worst observed case with wide margin.
2. Delete the 5 swarm shard files first — the harness resumes at row level and the failed
   rows are already written, so it would otherwise skip them as present:
   ```bash
   rm results-HPC/hpc-shards/frontier-v2.1-hpc-14b-swarm-t{1..5}.jsonl
   ```
3. Re-run swarm only (array elements 10–14):
   ```bash
   sbatch --array=10-14 scripts/job_frontier_a40_n5_sharded.sbatch
   ```
4. Verify on completion: `backend_exception == 0` across all swarm shards, 36 rows each.

Monolithic and agentic shards (elements 0–9) stand as-is — do not re-run; they are clean
and re-running would only burn A40 hours and change nothing.

**Not a pre-registration amendment.** `LLM_TIMEOUT_S` is a per-machine hardware knob, not a
pinned scientific parameter (factory.py:66-70), and is not covered by `config_hash`. No
decoding parameter changes, so re-run rows remain directly comparable to the existing
monolithic/agentic rows and to M4/M5.

## Secondary observations (not blocking)

- **`latency_s = 0.0` on exception rows** discards the real elapsed time. Had the true ~600 s
  been recorded, this would have been obvious at a glance instead of needing the
  `peer_latencies_s` staircase to diagnose. Worth stamping elapsed time even on the
  exception path.
- **`parallel_speedup` reports median 2.03** on a strictly-serialized server. It is computed
  as `sum(peer_latencies_s) / wall_s`, but those peer latencies include queue wait, so it
  measures queueing overlap rather than genuine concurrency. Expected given the pinned
  deployment (the sbatch header documents the serialization as deliberate), but it should
  **not** be read or reported as a speedup.
- The 600 s ceiling may also be quietly truncating the tail of the *surviving* swarm rows'
  behaviour distribution; the re-run at 1800 s will show whether the 8 rows clustered at
  550–595 s were themselves near-misses.
