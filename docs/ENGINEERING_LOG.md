# Engineering & Validation Log

Running record of the troubleshooting, methodological corrections, and A/B
validation trials performed while building the harness and running the
multi-machine study. Written for inclusion in the final report. Companion to
`PRE_REGISTRATION.md` (frozen design) and `docs/TASK_TIERS.md`.

Last updated: 2026-07-14.

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
| B6 | Long reasoning turns time out on slow hardware | client read timeout hardcoded at 600 s; a full `max_tokens=6144` turn at the M4's ~9.65 tok/s needs ~640 s → `backend_exception` timeout mid-trial | `LLM_TIMEOUT_S` env override (default 600; a per-machine hardware knob, **not** a pinned science param) | unit test asserts the override reaches the client; M4 trial re-ran clean at 1800 s |

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

## 7. M4 Mini (Apple Metal) monolithic cell — completed

**M4 Mini (Metal, 24 GB), Ollama, deepseek-r1:14b, frozen frontier-v2, monolithic, N=1.**
Scoped to monolithic-only — the full 3-backend run was ~13–16 h on this box (see
latency below), and the M4 cell's value is (a) a cross-hardware **reproducibility
check** and (b) an **Apple-Metal-vs-CUDA latency** point, both of which a single-pass
cell delivers. Output isolated under `results/m4-ollama/`.

### Accuracy — identical 36 frozen items, temp 0 (reproducibility check)
| domain | M4 (Metal) | Shadow (CUDA) |
|---|---|---|
| math (AIME 2025) | 6/12 = 50% | 3/12 = 25% |
| code (BigCodeBench-Hard) | 4/12 = 33% | 5/12 = 42% |
| multihop (MuSiQue+context) | 8/12 = 67% | 8/12 = 67% |
| **overall** | **18/36 = 50%** | **16/36 = 44%** |

Aggregate accuracy is close (50% vs 44%, both near the N=5 calibration of 52%) and
**multihop is identical**. The math/code per-domain swings are **N=1 sampling noise**:
temp 0 does *not* force identical single outputs across Metal and CUDA — a small early
divergence in the reasoning chain flips the final answer — but the distributions line
up. **Takeaway:** for this reasoning model, cross-accelerator results reproduce *in
aggregate*, not *per-item*; per-item cross-hardware comparisons need N > 1.

### Latency — the Apple-Metal cost
| host | median / call | throughput | wall (36 monolithic) |
|---|---|---|---|
| M4 Mini (Metal, 24 GB) | 322 s | ~10.4 tok/s | 3.1 h |
| Shadow (RTX A4500, CUDA) | 71 s | ~39 tok/s | 0.7 h |

The M4 is **~4.6× slower per call (~3.8× fewer tok/s)** on this 14B reasoning workload —
why the full 3-backend run projected to ~13–16 h and was scoped to monolithic. This is
also what surfaced **B6**: at ~10 tok/s a full 6144-token turn exceeds the old 600 s
client timeout.

### Why ~4×: memory bandwidth, not compute (and it's the *base* M4)
Token generation is **memory-bandwidth-bound** — each token streams the full ~9 GB (Q4)
of weights through memory, so decode speed ≈ *bandwidth ÷ model size*. The fingerprint:
M4 tok/s is **flat at 10.4 ± 1.3** across output lengths from 175 to 6144 tokens — a
hardware ceiling, not a calibration/config effect. Both machines land near the ceiling
their bandwidth predicts:

| host | mem bandwidth | ceiling (BW ÷ 9 GB) | observed | % of peak |
|---|---|---|---|---|
| base M4 Mini (this box) | ~120 GB/s | 13.3 tok/s | 10.4 | 78% |
| RTX A4500 (Shadow) | ~640 GB/s | 71 tok/s | 39.0 | 55% |

The raw bandwidth ratio is ~5.3×; it narrows to the observed ~4× because the M4 runs
closer to its ceiling (78% vs 55%). **Report caveat:** this is the *base* M4 (10 GPU
cores, ~120 GB/s) — Apple's lowest-bandwidth tier. An M4/M5 **Max** (~400–550 GB/s)
would be ~1.3× the A4500, i.e. roughly on par. The 4× is a property of *this specific
low-bandwidth box*, not "Apple Silicon vs a workstation GPU."

---

## 8. Agentic "false revision" — the verifier approves, the framework doesn't hear it

**Discovered 2026-07-14** by live-monitoring the in-flight local v2.1 confirmatory
sweep, investigating why agentic trailed monolithic/swarm by 10–25 points on math.

### 8.1 Mechanism

The pinned verifier prompt (`prompts/agentic/verifier_system.txt`) requires the
verdict on the **first line** ("either APPROVE or REVISE"), and the backend parses it
literally — `backends/agentic.py`:

```python
approved = resp.text.strip().upper().startswith("APPROVE")
```

DeepSeek-R1 is a reasoning model: it explains first and verdicts later, so its
approvals routinely fail `startswith`. Two paths produce the failure:

1. **Protocol non-compliance in visible output** — the verifier writes
   "The candidate answer correctly … APPROVE … $\boxed{70}$": verbally an approval,
   parsed as a revision request.
2. **Thinking-fallback text** — when a verifier turn exhausts `max_tokens`, the
   Ollama `thinking` fallback (§B5-adjacent, `backends/llm_client.py`) returns raw
   chain-of-thought as the turn text. CoT never begins with "APPROVE", so an
   exhausted verifier turn is *structurally guaranteed* to parse as REVISE.

A false revision then forces another Executor→Verifier loop: the executor is told to
revise an already-approved answer, each turn draws from a fresh 6144-token budget
(compounding the §5/§7 exhaustion mode), and the run frequently ends with an **empty
final answer** — a correct, verbally-approved draft destroyed by the loop that was
supposed to protect it.

### 8.2 Evidence (local v2.1 sweep, snapshot at 95 agentic rows)

- **20/95 agentic rows (21%)**: first verifier turn contains APPROVE but parsed
  `approved: false`. 15 of the 20 scored wrong.
- **≥5 math rows**: executor draft **correct** AND verifier verbally approved —
  row still scored 0.
- Cleanest exhibit, `fx2-mathA-001` (gold: 70), identical in all 5 trials (temp 0):
  executor → "$\boxed{70}$" ✓; verifier → "…is indeed 70. APPROVE. $\boxed{70}$";
  trace records `approved: false`; loop 2 runs; final answer: **empty**
  (`format_error`, 9,965 tokens spent).
- Cost signature: agentic averages **8,463 output tokens/run vs monolithic's 4,436**
  — 2× the spend for negative marginal accuracy. Swarm spends more still (13,281)
  but its peers are near-clones at temp 0 (see the swarm-voting finding, wiki E12:
  greedy decoding ignores the per-peer seed offsets), so it effectively re-runs
  monolithic and inherits monolithic's accuracy — whereas agentic's control flow
  can actively *destroy* a correct answer through the parse gap. Same tokens
  wasted, asymmetric damage.
- Back-of-envelope: recovering the false-revision rows would lift agentic from ~29%
  to roughly monolithic parity on the rows collected so far.

### 8.3 Decision — no mid-run fix; pre-declared counterfactual instead

The prompt and the parse rule are **pinned** (bytes hashed into every row) and every
environment (v1 baseline, Shadow, M4, local, HPC) runs identical code — a mid-run
"fix" would fork the dataset and destroy cross-environment comparability. Instead
(Amendment Log, 2026-07-14):

- **Primary metric unchanged** — it measures the framework *as deployed*.
- **Secondary counterfactual re-parse over saved traces**, rule fixed before any
  result was computed: replay each agentic trace; at the first verifier turn whose
  *lenient* verdict is APPROVE (last standalone APPROVE/REVISE token in the visible
  text decides; neither → REVISE), grade that turn's candidate with the pinned
  grader; otherwise keep the recorded outcome. Report both numbers side by side.
- Optional exploratory arm later (post-confirmatory, env-flag-stamped like the swarm
  probe knobs): rerun with lenient parsing live, to measure the loop's value when
  the approval channel actually works.

### 8.4 Why this is a finding, not just a bug

The failure is the *interaction* between (a) reasoning models' weak compliance with
strict output protocols and (b) agent frameworks that key on exact tokens for
control flow. Monolithic and swarm are structurally immune — nothing in their paths
parses a control token from model text; majority voting needs only comparable
answers. The agentic architecture is the only one whose **control flow** runs
through the model's prose, and that channel is exactly what a reasoning model's
style (and the thinking-field failure mode) corrupts. For the paper: part of
"agentic underperforms" decomposes into *verifier judgment cost* vs
*protocol-compliance loss* — the counterfactual separates the two.
