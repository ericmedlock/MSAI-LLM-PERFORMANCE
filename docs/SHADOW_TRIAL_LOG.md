# Shadow PC Trial — Engineering & Methodology Log

**Date:** 2026-07-12 · **Operator:** ericmedlock (Claude Code driving) · **Purpose of trial:**
first-ever NVIDIA/CUDA environment for this harness — validate the **Ollama provider path** and
the **CUDA/NVML GPU-telemetry fields** ahead of the university HPC sweep and the Azure cloud cell.

This log is written to be dropped into the final report. It records what was run, every issue hit,
the root cause, the fix, and the verification — plus the A/B measurements that came out of the
troubleshooting. Nothing here changes any pinned scientific parameter; all fixes were to tooling
(`scripts/setup.sh`) or operations, not to `config/config.yaml`, `tasks/`, or `prompts/`.

## 1. Environment

| Item | Value |
|------|-------|
| Machine | Shadow.tech **Power Pro** cloud PC, Windows 11 |
| GPU | **NVIDIA RTX A4500**, driver 596.72, CUDA 13.2 |
| GPU VRAM | **20 GB** (20470 MiB) — note: the printed guide assumed the 24 GB A4500 variant; this is the 20 GB variant. Immaterial (9 GB model fits comfortably). |
| CPU / RAM | AMD Family 25 (Zen 3), 28 GB system RAM |
| Model server | **Ollama** 0.31.2 @ `http://localhost:11434` |
| Model | **DeepSeek-R1-Distill-Qwen-14B**, Q4_K_M (~9 GB); Ollama tag `deepseek-r1:14b`; canonical `deepseek-r1-14b-distill-q4_k_m` |
| Config hash | `5031ae81369ce37b` (stamped on all rows) |
| Task suite | frozen **frontier-v2** tier, 36 items (12 math / 12 code / 12 hop) |
| Design | 36 tasks × 3 architectures (monolithic / agentic / swarm) × N=1 = **108 runs** |

Offline test suite before the run: **112 passed, 2 deselected** (matches the pinned expectation).

## 2. Issue #1 — GPU telemetry recorded as NULL (the headline defect)

**This is the exact failure the trial existed to catch.**

- **Symptom.** The first recorded row had `telemetry.peak_vram_mb`, `avg_gpu_util_pct`, and
  `gpu_power_w` all `null`, while CPU/RAM telemetry was present.
- **Root cause.** The NVML Python binding (`pynvml`, provided by `nvidia-ml-py`) was **not
  installed**. It is intentionally split into `requirements-cuda.txt` because it does not exist on
  Apple/Metal, but `scripts/setup.sh` only ran `pip install -r requirements.txt` — it never
  installed the CUDA extras on any profile. Because the harness was developed on the M5 Max
  (Metal), the NVML code path in `harness/telemetry.py` (`CudaCollector`) had **never been
  exercised** until this first NVIDIA host. With `pynvml` absent, `_HAS_NVML=False`, the collector
  acquires no device handle, and every GPU field returns `None`.
- **Fix.** Patched `scripts/setup.sh` to install `requirements-cuda.txt` whenever `nvidia-smi` is
  present (covers shadow / hpc / Azure); installed it into the live venv to proceed. *No science
  change — telemetry deps only.*
- **Verification.** NVML end-to-end via the harness collector returned `peak_vram_mb≈11857`,
  `avg_gpu_util_pct≈88`, `gpu_power_w≈198`. The stale null-telemetry row was discarded and the run
  restarted clean. **All 108 final rows carry populated CUDA/NVML telemetry** (see §7).
- **Downstream impact.** The same fix pre-empts the identical failure on the HPC and Azure CUDA
  hosts. Had it gone unnoticed, the entire GPU-telemetry objective (VRAM / utilization / power)
  would have been silently empty.

## 3. Issue #2 — Orphaned-runner contention (A/B on latency)

Surfaced while investigating "does this seem slow for an A4500?"

- **Symptom.** Duplicate `(task_id, backend, trial_idx)` rows appeared despite N=1, and monolithic
  latency ballooned from **~53 s to ~394 s (≈7×)** for the same class of single-call task.
- **Diagnosis.** Four `python -m harness.run` processes were writing the same output file at once.
  Cause: on Windows, stopping a background run killed the Git-Bash wrapper but **orphaned the
  child Python process**, which kept running; a second run was then started, and the swarm backend
  additionally spawns transient peer subprocesses. Multiple runners contended for the single GPU
  (one 14 B model loaded), so every request slowed proportionally, and independent runners
  double-wrote rows.
- **Resolution.** Killed all `harness.run` workers, wiped the contention-contaminated results file,
  and restarted a **single** clean run. Confirmed exactly one runner tree (verified via
  parent/child PIDs: the apparent "second" process is a legitimate child of the one runner) and
  **0 duplicate rows** thereafter.
- **A/B result.** Contended monolithic ≈ **394 s** vs clean monolithic ≈ **47–73 s**. This
  established that the A4500 was never the bottleneck — the slowdown was self-inflicted
  concurrency, not hardware.
- **Operational note for HPC.** Ensure only one runner writes a given output file; the row-level
  checkpoint makes a single serial runner the correct pattern (parallelism belongs across GPUs/
  nodes, not across processes sharing one GPU + one file).

## 4. Issue #3 — Shadow disconnect/timeout & resume (checkpointing validation)

- **Behavior.** Shadow shuts the VM down a few minutes after the client disconnects; this happened
  **mid-run twice**, once with the VM rebooting entirely.
- **Result.** Row-level checkpointing held: **34 of 108 rows survived** the reboot, and simply
  re-running `bash scripts/run_trials.sh shadow` **resumed from the checkpoint with zero data loss
  and zero duplicates** (verified: 34 unique cells, 0 null-telemetry, before resuming). The run
  later completed 108/108 cleanly.
- **Takeaway.** The resumable/idempotent design is validated for long unattended runs — important
  for the multi-hour HPC sweep where requeues are expected.

## 5. Shadow A4500 vs Apple M5 Max — matched comparison

**Scope caveat (important).** The prior M5 Max frontier-v2 data (`results/frontier-v2-calib-14b.jsonl`,
env=local, LM Studio) is a difficulty **calibration** run: **monolithic only** (62 tasks × N=1–5,
0 agentic / 0 swarm rows). So the *only* apples-to-apples comparison is **monolithic**. The Shadow
trial is therefore the **first full 3-architecture (monolithic + agentic + swarm) frontier-v2 run on
any machine**; agentic/swarm have no M5 Max counterpart on this tier.

### 5a. Accuracy — monolithic, same 36 frontier-v2 tasks, N=1

| domain | Shadow A4500 (Ollama/CUDA) | M5 Max (LM Studio/Metal) |
|--------|:--------------------------:|:------------------------:|
| math   | 3/12 | 5/12 |
| code   | 5/12 | 6/12 |
| hop    | 8/12 | 8/12 |
| **TOTAL** | **16/36 (44%)** | **19/36 (53%)** |

Per-cell agreement across the 36 monolithic cells: **69% (25/36)** identical verdict; disagreements
roughly balanced (M5 correct where Shadow wrong on 7; Shadow correct where M5 wrong on 4).

**Read:** 16 vs 19 is a 3-item swing on 36 at N=1 — **within noise**, and not purely hardware. The two
environments serve the *nominally* identical model through **different servers** (Ollama vs LM Studio),
which can differ in GGUF build, tokenizer, and temperature-0 tie-breaking. This is the documented
Metal-vs-CUDA cross-environment threat (pre-reg §S12), not a capability gap.

### 5b. Throughput — monolithic

| | Shadow A4500 (Ollama/CUDA) | M5 Max (LM Studio/Metal) |
|---|:---:|:---:|
| mean tokens/s | **36.9** | **40.4** |
| mean latency  | **73 s** | 78 s |
| n (rows)      | 36 | 310 |

**Conclusion:** effectively equal (~7% apart), latencies within ~7%. Both are memory-bandwidth-bound on
the ~9 GB model (A4500 640 GB/s GDDR6; M5 Max ~400–550 GB/s unified). The A4500 is **not slow** — the
earlier apparent slowness was the §3 contention bug. (For reference, the M5 Max baseline suite ran
~50.8 tok/s; the easier tasks emit shorter outputs. Shadow's all-108 aggregate was 37.7 tok/s, dragged
down by the long agentic/swarm reasoning cells — per-call decode rate is unchanged.)

*Supersedes an earlier rougher "~43.5 vs ~41 tok/s" estimate; this matched-manifest monolithic
comparison (36.9 vs 40.4) is the correct figure.*

## 6. Finding — agentic "empty answer" / `format_error` (mono-vs-agentic bias investigation)

Triggered by the observation that **monolithic (16/36) edged agentic (14/36)** — a counter-intuitive
result for a self-correction architecture, so it was investigated for an unintended bias.

- **Not a uniform grading bias.** The deficit is **domain-specific** — agentic *beats* monolithic
  on math (5 vs 3) and collapses on code (2 vs 5). A parsing/grading bug would depress agentic
  uniformly across domains; it does not.
- **Mechanism (genuine).** The agentic verifier *reasons about* correctness but does not *execute*
  code. On math it catches arithmetic/logic slips (helps); on code it lacks ground truth and
  **over-corrects working solutions into broken ones** — directly observed on `fx2-codeH-008`,
  where a passing `shutil.copy2(src_str, dest_file)` was rewritten into a failing
  `copy2(src_path, dest_path)`. Those rows are `reasoning_error` with complete code blocks; the
  grader is correct.
- **A separate, fixable artifact.** **4 items** (`codeH-007`, `codeH-011`, `mathA-002`, `mathA-005`)
  produced an **empty final answer despite 9.7k–24.5k generated tokens** (`mathA-005` hit exactly
  24576 = the max-token ceiling with the loop's max `action_count=4`) → auto-graded `format_error`
  (automatic fail). Two of the four are items monolithic got **right**, so this unfairly widens the
  gap. Root-cause hypotheses (token-budget exhaustion across the loop vs. final-answer extraction
  from the multi-turn trace) and read-only investigation steps are captured in
  [`results/POST_RUN_NOTE_agentic_empty_answer.md`](../results/POST_RUN_NOTE_agentic_empty_answer.md).
  **To resolve before the HPC N=5 run.** Any `max_tokens` change is a pre-registration amendment.
- **Statistical caveat.** At **N=1**, 16 vs 14 (a 2-item swing on 33 comparable items) is **not
  significant** — this is directional only. The N=5 HPC run is the confirmatory test.

## 7. Final results (108/108, integrity-checked: 0 duplicates, 0 null-telemetry)

**Accuracy — domain × architecture:**

| domain | monolithic | agentic | swarm |
|--------|-----------:|--------:|------:|
| math   | 3/12 | 5/12 | 6/12 |
| code   | 5/12 | 2/12 | 3/12 |
| hop    | 8/12 | 7/12 | 9/12 |
| **TOTAL** | **16/36 (44%)** | **14/36 (39%)** | **18/36 (50%)** |

Directional read (N=1, not significant): **swarm > monolithic > agentic** overall, but the value of
an architecture is **domain-dependent** — swarm leads on every domain; agentic helps on math and
hurts on execution-graded code.

**GPU telemetry — CUDA/NVML, the primary objective (all n=108):**

| field | min | median | max |
|-------|----:|-------:|----:|
| `peak_vram_mb` | 11401 | 11530 | 11895 |
| `avg_gpu_util_pct` | 62.2 | 87.8 | 91.8 |
| `gpu_power_w` | 154.2 | 193.9 | 198.1 |

**Latency (mean per architecture):** monolithic 73 s · agentic 198 s · swarm 230 s. Total compute
≈ 5.0 h of model time (wall time longer due to two Shadow reboots). Total output tokens: 738,962.

## 8. Verdict

- **Primary objective PASS:** the Ollama provider path and the CUDA/NVML telemetry fields are
  validated on real NVIDIA hardware — 108/108 rows carry non-zero VRAM / utilization / power.
- **Tooling hardened for HPC/Azure:** `setup.sh` now installs the NVML dependency on any CUDA host,
  so the telemetry bug cannot recur on the next environments.
- **One open item before HPC:** the agentic empty-answer/`format_error` extraction issue (§6).
- **Data provenance:** all 108 rows plus the host profile committed and pushed to `main`.

## Artifacts

- Results: [`results/frontier-v2-shadow-trial-14b.jsonl`](../results/frontier-v2-shadow-trial-14b.jsonl) (108 rows)
- Host profile: [`results/host/shadow.json`](../results/host/shadow.json)
- Open follow-up: [`results/POST_RUN_NOTE_agentic_empty_answer.md`](../results/POST_RUN_NOTE_agentic_empty_answer.md)
- Tooling fix: `scripts/setup.sh` (CUDA telemetry-deps install)
