# Engineering & Validation Log

Running record of the troubleshooting, methodological corrections, and A/B
validation trials performed while building the harness and running the
multi-machine study. Written for inclusion in the final report. Companion to
`PRE_REGISTRATION.md` (frozen design) and `docs/TASK_TIERS.md`.

Last updated: 2026-07-12.

---

## 1. Central finding: the original task suite could not test the architectures

### 1.1 Symptom — monolithic "wins," swarm looks "dominated"

The pre-registered v1 baseline suite (`tasks/manifest.json`: 15 objective items —
GSM8K, HumanEval, HotpotQA) at N=5 produced:

| architecture | accuracy | latency | tokens | note |
|---|---|---|---|---|
| agentic | 100% | 32.5 s | 1961 | most expensive |
| **monolithic** | **93%** | **15.2 s** | **832** | **cheapest → Pareto-optimal** |
| swarm | 93% | 32.9 s | 2649 | most expensive, no accuracy gain → "dominated" |

Read naïvely, this says **"use monolithic — the extra architectures only add cost."**

### 1.2 Why that conclusion is invalid

The pinned model scored **93–100% single-pass** on these tasks. That is *above the
ceiling* where added machinery can help:

- **Agentic** (Executor→Verifier) can only help when single passes make
  **correctable** errors. At 93–100% there is almost nothing to correct.
- **Swarm** (parallel vote) only lifts accuracy in a **moderate band** (single-pass
  ≈ 0.4–0.7), where aggregating diverse samples overcomes noise. Far above that
  band, every peer already agrees on the right answer, so voting changes nothing.

So **monolithic did not win because it is the better architecture — it won because
the tasks were too easy for architecture to matter.** Swarm looking "dominated" is a
**task-selection artifact**, not a property of the architecture: on easy tasks the
only differentiator left is cost, and the simplest topology is cheapest. The result
"monolithic is best" was **right for the wrong reason.**

This is a validity threat, not a finding: the experiment as first run **cannot
discriminate** between the architectures because the task set never enters the regime
where they differ.

### 1.3 The correction — task tiers and the 0.4–0.7 calibration band

The pre-registered hypothesis is that architecture superiority is **task-dependent**.
To observe it, the task set must span the regime where it appears. We added a
**frontier tier** and a **pre-declared, empirical selection rule**:

> Keep an item **iff** monolithic single-pass accuracy for the serving model lands
> in **~[0.4, 0.7]** at N ≥ 5. Items the model always gets right (no headroom) or
> always wrong (unreachable) are **dropped, not tuned** — this prevents
> cherry-picking a favorable story.

The baseline tier remains a legitimate result in its own right (*on easy tasks,
architecture doesn't matter — use monolithic*). The frontier tier is what turns
"we measured overhead" into "we found where each architecture wins." See
`docs/TASK_TIERS.md`.

---

## 2. Building a hard-enough tier — and the model-relativity of "hard"

### 2.1 Authored candidates were still too easy

A first, hand-authored frontier candidate set (9 items) was measured against the
dev model **gemma-4-e4b** (see §3.2): **27/27 = 100% monolithic** → every item lands
*above* the band → all dropped. Authoring "hard" tasks by hand failed; the model
solved them all.

### 2.2 Externally-calibrated tasks; SWE-bench and GAIA evaluated and rejected

We pulled from public, community-calibrated benchmarks that **fit the objective
graders**:

| domain | source | grader |
|---|---|---|
| math | MATH-500 (level ≥ 3, integer answers), later **AIME** in the frozen v2 tier | numeric last-value |
| code | MBPP-sanitized (unit-test graded) | run `check(candidate)` |
| multihop | MuSiQue (2–4 hop) | normalized-string match |

**SWE-bench and GAIA were considered and rejected** — an explicit scope decision:

- **SWE-bench** grades by cloning a repo and running its test suite in Docker. This
  harness grades **in-process** (a single function or a string/numeric answer); it
  has no repo-execution sandbox, so SWE-bench cannot plug into the grader.
- **GAIA** is gated and most items require **live web/tool use** and file
  attachments — incompatible with a single-prompt, no-tool harness.

Every imported item was **validated offline by running the real grader** before any
model touched it (code reference solutions execute; math/multihop gold answers
self-grade), so authoring bugs are caught before burning compute.

### 2.3 "Hard" is relative to the serving model

The externally-sourced tier is much harder than baseline, but *how* hard depends on
the model. On the 4B dev model (gemma-4-e4b) it was **too hard** (near the bottom of
the range); it is aimed at the **14B pinned model**, where it lands *in* the band
(§5). **Lesson recorded in the method:** calibrate the frontier tier against the
*actual serving model* before freezing — a set that is in-band for one model is not
for another.

The **frozen** tier (`tasks/frontier_v2_manifest.json`, immutable by
pre-registration) is **36 items: 12 math (AIME), 12 code, 12 multihop.**

---

## 3. A/B trials (serving stack, model tier, hardware)

### 3.1 Serving stack: LM Studio (OpenAI-compatible) vs native Ollama

Two provider paths exist: `openai` (LM Studio / vLLM / llama.cpp, `/v1/chat/completions`)
and `ollama` (native `/api/chat`). We validated both. The Ollama path had a latent
bug that made its real-model validation silently vanish — see §4 (B5). After the fix,
all three backends and both live integration tests pass against Ollama.

### 3.2 Model tier: dev vs study

| role | model | why |
|---|---|---|
| dev / plumbing | **gemma-4-e4b** (4B) | fast iteration on the harness; too capable-per-size, so it over-solved authored "hard" tasks (§2.1) |
| study (pinned) | **deepseek-r1-14b (distill, Q4_K_M)** | the frozen model; used across all study environments |

### 3.3 Hardware / environment matrix

| env | machine | accelerator | serving | status |
|---|---|---|---|---|
| dev | Apple M4 Mini, 24 GB | Metal | LM Studio → Ollama | harness dev + this trial |
| (orig. dev) | Apple M5 Max, 48 GB | Metal | LM Studio | superseded (downsized box) |
| shadow | AMD/NVIDIA, 28 GB | CUDA | Ollama | **frontier-v2 @ 14B run complete** |
| hpc | Linux cluster | CUDA | Ollama (no-root) | staged |

The dev box was **downsized mid-study (M5 Max 48 GB → M4 Mini 24 GB)**, which forced
the model swap and the machine-portability work (self-bootstrapping `setup.sh`).

---

## 4. Bugs found and fixed (root cause → fix → verification)

| # | Bug | Root cause | Fix | Verified by |
|---|---|---|---|---|
| B1 | Reports mislabel the model on dev/override runs | canonical `model.tag` was not `.env`-overridable; rows showed the frozen tag, not what ran | `MODEL_TAG`/`MODEL_QUANT` override (`ModelConfig.resolved`) | unit test; dev report shows served model |
| B2 | Judge cannot score frontier rows | `harness.judge` loaded only the baseline manifest → no gold context for frontier items | `--manifest` (repeatable) via `load_task_index` | `test_judge` merges both manifests |
| B3 | CLI tests not hermetic | `main()` reads `./.env`; a dev `.env` changed the asserted banner | autouse fixture neutralizes ambient `.env` | offline suite green with a dev `.env` present |
| B4 | Tests + dev runs rewrite **frozen** provenance | host sidecar written to fixed `config.results_dir` regardless of `--output` → `results/host/*.json` + `hosts.csv` clobbered on every runner test | co-locate the sidecar with the **output path** | regression test; frozen provenance stays clean after a full test run |
| B5 | **Ollama real-model validation silently skipped** | integration liveness probe used `/models` (OpenAI-only); Ollama returns 404 there (it uses `/api/tags`) → `_reachable` false → tests skipped on a *live* Ollama | provider-aware probe (`/api/tags` for ollama) + load `.env` in the fixture | 2 integration tests now **pass** vs Ollama; offline regression guard added |

### 4.1 Data-integrity incident (recorded, not trusted)

A first attempt to measure the external tier on gemma-4-e4b produced a headline
"9%" (code 0% / multihop 0%). On inspection this was **corrupted**: LM Studio dropped
connections mid-run (`RemoteDisconnected`, ~0-token `backend_exception` rows), so the
low score was mostly harness/serving failure, not real model misses. **The number was
discarded**; conclusions about the external tier come from the stable 14B runs (§5).
General practice adopted: inspect `error_category` / token counts before trusting any
aggregate.

---

## 5. Validation of the correction — architectures differentiate on hard tasks

**Shadow PC, frozen frontier-v2 (36 items), deepseek-r1-14b, N=1:**

| architecture | overall | code | math | multihop |
|---|---|---|---|---|
| **swarm** | **47%** | 25% | 50% | **75%** |
| monolithic | 42% | **42%** | 25% | 67% |
| agentic | 38% | 17% | 42% | 62% |

The model now sits **inside the 0.4–0.7 band** (38–47% overall). Consequences:

- The "monolithic wins" artifact from §1 **disappears** — swarm now leads overall,
  and on **math** and **multihop** both swarm and agentic beat monolithic (voting /
  verification pay off where single passes are shaky).
- On **code**, monolithic is best and **agentic is worst (17%)** — the Executor→Verifier
  loop appears to *break already-correct code*. Flagged for investigation (candidate:
  verifier over-edits passing solutions).
- N=1 is exploratory (noisy); a confirmatory N=5 pass is planned (`run_trials.sh hpc`).

This is the payoff of the methodological correction: on appropriately hard tasks the
architectures separate and the trade-offs (accuracy vs cost, and which topology helps
which domain) become measurable — which the original easy suite made impossible.

---

## 6. Test-validity note: logic tests vs real-model validation

Two distinct layers, not to be conflated:

- **Offline suite (113 tests, mocked model via `FakeLLMClient`)** — tests harness
  *logic* (grading, voting, agentic loop, telemetry, resume). Deterministic and
  **LM-Studio/Ollama-independent**; this is what Shadow/HPC run (`pytest -m "not
  integration"`). "Passing with a dead endpoint" is **not** evidence the system talks
  to a model — the tests never call a real one (the sole incidental network call,
  provenance `_loaded_models`, degrades gracefully and is not asserted).
- **Integration tests (real model)** — genuinely exercise a live server; they
  `skip` (not "pass gracefully") when none is reachable, so they never give false
  confidence. Now pass against **both** LM Studio and Ollama.

---

## 7. This machine's trial (in progress)

**M4 Mini (Metal, 24 GB), Ollama, deepseek-r1:14b, frozen frontier-v2, N=1** — adds
the Apple-Metal hardware point to the cross-machine comparison (vs Shadow/CUDA). Output
isolated under `results/m4-ollama/` so provenance does not collide with the frozen
`local` cell. Results and per-domain breakdown to be appended here on completion.
