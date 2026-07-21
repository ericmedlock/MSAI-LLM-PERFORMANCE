# A40 anomaly: diagnose → fix → deploy-v2 re-run (operational playbook)

**Task brief executed 2026-07-21** (M5-side session). Everything below is
pre-built and pushed; Eric runs the numbered commands on the Starlight login
node. Nothing runs on the HPC from the Mac.

## The problem (recap)

A40 serves the pinned 14B Q4_K_M at **17.5 tok/s** at "83% util" — half of a
weaker A4500 (37.7), on hardware whose ~696 GB/s bandwidth should deliver
35–50 tok/s at batch-1 decode. High-util+low-throughput is the signature of
small kernels interleaved with CPU-side stalls. Downstream: all A40
energy-per-correct figures (43.4/79.8/117.4 kJ) are inflated ~2×, and the B6
timeout incident destroyed 36% of a swarm cell with survivorship-biased
leftovers. Ranked candidate causes and full protocol: the task brief
(mirrored in the vault) and this playbook's scripts.

## What was changed in the harness (already merged — applies everywhere)

| change | where |
| --- | --- |
| Client read-timeout default 600 s → **1800 s** (worst pre-registered row: 495–741 s/attempt; queued peers wait behind it) | `backends/llm_client.py`, `backends/factory.py` |
| **Retry-with-backoff** on transient transport errors: connection errors ×3 (5 s/15 s backoff), 502/503/504 ×3, read-timeout ×1 — surviving failures still raise and are recorded as scored `backend_exception` rows, never dropped | `backends/llm_client.py::_post_with_retry` (tested) |
| **Row-completeness assertion**: `scripts/validate_cell.py` — expected = tasks × backends × trials, zero missing/dup keys, explicit failure counts, single config hash. Exit 1 on any silent loss | new script; also gated inside the re-run pipeline |

## Step 1 — Diagnose (read-only, ~30 min, 1 GPU)

```
git pull
sbatch scripts/hpc_a40_diagnose.sbatch
```

Writes `results-HPC/diagnostics/<jobid>/` — env snapshot (Slurm CPUs, clocks,
power limit, PCIe, MIG), offload report + `ollama ps`, single-stream tok/s
under `nvidia-smi dmon` + CPU watch, **llama-bench hardware isolation** (if
installed — the bundle says how to add it if missing), 1-vs-3-stream
concurrency test, and an auto-printed decision tree in `SUMMARY.txt`.
Commit the bundle (`git add results-HPC/diagnostics && commit && push`) so the
M5 side can read it.

**Decision tree:** llama-bench fast (≥35) → deployment config problem (step 2
defaults are the fix). llama-bench also slow → node problem (power cap /
clocks / CPU count / contention) — fix the Slurm/node side first, then step 2.

## Step 2 — Probe + gate (study-integrity rule: a fixed deployment is a NEW deployment)

```
bash scripts/hpc_a40_v2_rerun.sh probe        # mono x 36 x trial-1, fixed deployment (~1-2 h)
bash scripts/hpc_a40_v2_rerun.sh probe-check  # THE GATE
```

The probe runs under the deploy-v2 configuration (`--cpus-per-task=8`,
`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_NUM_PARALLEL=3`, `LLM_TIMEOUT_S=1800`),
pinned science untouched. The gate compares against the **same-seed trial-1
rows** of the existing cell (an N=1 probe vs the N=5 mean trips on trial noise
alone — verified) and hard-stops (exit 2) if same-seed accuracy moves > 8 pts:
that means the deployment change altered effective difficulty and the
**author** decides about a re-freeze, not the pipeline. It also warns if
throughput is still < 30 tok/s (fix didn't land — go back to diagnostics).

## Step 3 — Full grid + validation (only after the gate passes)

```
bash scripts/hpc_a40_v2_rerun.sh full         # 15 shards (3 arch x 5 trials), ~3-5 h
bash scripts/hpc_a40_v2_rerun.sh validate     # completeness gate -> merge -> before/after table
```

Everything lands in `results-HPC/a40-deploy-v2/` — never merged with the
as-deployed cell (`frontier-v2.1-hpc-14b-n5.jsonl`), which **stays in the
paper** as the "deployment properties invert energy economics" evidence. Every
shard writes a `.deploy.txt` sidecar (Slurm CPU alloc, power limit, SM clock,
PCIe link, `OLLAMA_*` env) so this deployment is fully characterized.
`validate` prints the acceptance-criteria one-pager automatically: per-backend
accuracy / tok/s / W / kJ-per-correct, before → after. Then:

```
git add results-HPC/a40-deploy-v2 && git commit -m "data(hpc): a40-deploy-v2 ..." && git pull --rebase && git push
```

## Acceptance criteria (from the brief)

- [ ] Root cause documented with evidence (diagnostics bundle committed)
- [ ] Single-stream ≥ 30 tok/s (target ≥ 37.7)
- [ ] 3-peer concurrent pattern, zero silent row loss (validate gate green)
- [ ] Probe + gate run BEFORE the full grid
- [ ] 540-row grid complete under `a40-deploy-v2`
- [ ] Before/after kJ-per-correct table produced (validate prints it)
- [ ] M5 session folds numbers into the paper (F10/F11 refresh; the 5–15×
      laptop-vs-datacenter claim is expected to compress — the honest number
      is the point; report both deployments)
