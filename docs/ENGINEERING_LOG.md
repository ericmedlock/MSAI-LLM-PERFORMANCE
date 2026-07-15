# Engineering & Validation Log

Running record of the troubleshooting, methodological corrections, and A/B
validation trials performed while building the harness and running the
multi-machine study. Written for inclusion in the final report. Companion to
`PRE_REGISTRATION.md` (frozen design) and `docs/TASK_TIERS.md`.

Last updated: 2026-07-15.

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
| **swarm** | **50%** | 25% | 50% | **75%** |
| monolithic | 44% | **42%** | 25% | 67% |
| agentic | 39% | 17% | 42% | 58% |

*(Corrected 2026-07-14: the overall column as first written (47/42/38) and agentic
multihop (62%) did not match the committed 108-row file; recounted from
`results/frontier-v2-shadow-trial-14b.jsonl` — swarm 18/36, mono 16/36, agentic 14/36,
agentic multihop 7/12.)*

The model now sits **inside the 0.4–0.7 band** (39–50% overall). Consequences:

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

## 7. M4 Mini (Apple Metal) cell — completed (frontier-v2.1, monolithic + swarm)

**M4 Mini (Metal, 24 GB), Ollama, deepseek-r1:14b, frozen frontier-v2.1, monolithic +
swarm, N=1.** Originally run on v2, then **realigned to v2.1** after the study re-sourced
the code domain (v2 code drifted to 33% on this Ollama stack — below band; v2.1 lands it
at 58%). Math + multihop task_ids are identical across v2/v2.1, so those monolithic rows
were kept; only code was re-run, plus swarm across all 36. Agentic was dropped on M4
(~27 min/cell → ~a day; left to Shadow/HPC). Output:
`results/m4-ollama/frontier-v2.1-m4-ollama-14b.jsonl` (72 rows, 0 errors).

### Accuracy — monolithic vs swarm (architecture comparison), N=1
| domain | monolithic | swarm |
|---|---|---|
| math (AIME 2025) | 6/12 = 50% | 5/12 = 42% |
| code (v2.1 re-source) | 7/12 = 58% | 7/12 = 58% |
| multihop (MuSiQue) | 8/12 = 67% | **10/12 = 83%** |
| **overall** | **21/36 = 58%** | **22/36 = 61%** |

- **Swarm edges monolithic overall (61% vs 58%)**, driven entirely by **multihop
  (83% vs 67%)** — parallel voting helps most where single passes are shaky but not
  hopeless. Code ties; math is within N=1 noise (swarm slightly lower).
- **Code validated in band at 58%** (was 33% on v2) — direct confirmation the v2.1
  re-source fixed the cross-stack drift on Ollama; all three domains now sit in/near
  the [0.4, 0.7] band, so the tier can differentiate architectures.
- N=1 → per-domain deltas are noisy, but the overall swarm ≥ monolithic direction
  matches the Shadow trend. Cross-hardware reproducibility spot-check held: monolithic
  math is 50% on both M4 and the (early) M5 Max v2.1 N=5 run.

### Latency — the Apple-Metal cost
| host | median / call | throughput | wall |
|---|---|---|---|
| M4 Mini (Metal, 24 GB) | 322 s (mono) | ~10.4 tok/s | mono 3.1 h; +swarm ~9 min/cell → full cell ~13 h |
| Shadow (RTX A4500, CUDA) | 71 s | ~39 tok/s | monolithic 0.7 h |

Swarm's 3 peers **serialize** on a single Ollama instance (one model, one generation at
a time), so a swarm cell ≈ 3× a monolithic turn. The M4 is **~4.6× slower per call
(~3.8× fewer tok/s)** on this 14B reasoning workload — why agentic (up to ~4 calls/cell)
was dropped. This also surfaced **B6**: at ~10 tok/s a full 6144-token turn exceeds the
old 600 s client timeout.

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

### 8.4 Counterfactual results (run 2026-07-14, after the local sweep completed)

`scripts/agentic_counterfactual.py`, rule exactly as pre-declared. Agentic rows only;
pinned numbers are the primary metric and remain the headline.

| environment | domain | pinned | counterfactual | delta |
|---|---|---|---|---|
| local (N=5) | math | 20/60 = 33% | 25/60 = 42% | **+8.3 pts** |
| local (N=5) | code | 30/60 = 50% | 30/60 = 50% | 0 |
| local (N=5) | multihop | 35/60 = 58% | 35/60 = 58% | 0 |
| local (N=5) | **overall** | 85/180 = 47.2% | 90/180 = 50.0% | +2.8 pts |
| shadow (N=1) | overall | 14/36 = 39% | 14/36 = 39% | 0 |

5 flips, all local, all math, all wrong→right; **zero right→wrong** (the lenient rule
never damaged a recorded success). Interpretation:

- On **math**, protocol-compliance loss explains agentic's *entire* deficit: the
  counterfactual (42%) lands at parity with monolithic (43%) and swarm (42%).
  The false-revision loop was destroying correct, approved AIME answers.
- On **code and multihop**, the deficit is *not* a parsing artifact — those gaps
  (and the residual overall gap, 50% vs monolithic's 56%) reflect the architecture
  itself: verifier judgment errors and budget burn on revision loops the verifier
  genuinely (if wrongly) requested.
- Shadow's poor agentic code result (17%) is untouched by the counterfactual —
  consistent with the earlier "verifier over-edits passing code" hypothesis
  (`docs/SHADOW_TRIAL_LOG.md`), a different failure mode from false revision.

### 8.5 Why this is a finding, not just a bug

The failure is the *interaction* between (a) reasoning models' weak compliance with
strict output protocols and (b) agent frameworks that key on exact tokens for
control flow. Monolithic and swarm are structurally immune — nothing in their paths
parses a control token from model text; majority voting needs only comparable
answers. The agentic architecture is the only one whose **control flow** runs
through the model's prose, and that channel is exactly what a reasoning model's
style (and the thinking-field failure mode) corrupts. For the paper: part of
"agentic underperforms" decomposes into *verifier judgment cost* vs
*protocol-compliance loss* — the counterfactual separates the two.

---

## 9. The N-trials flaw: N=5 measured (almost) nothing

**Status: FLAW CONFIRMED — pinned design change + full data regeneration (2026-07-15).**
This is the reason the study changed approach and regenerated all trial data.

### 9.1 Symptom

N=5 runs cost 5× the compute, but ~98% of cells returned the **identical verdict on
all five trials**:

| N=5 dataset | multi-trial cells | per-cell outcome spread | cells with *any* variance |
|---|---|---|---|
| `results/frontier-v2-calib-14b.jsonl` | 70 | 0/5 ×21 · **1/5 ×1** · **4/5 ×1** · 5/5 ×47 | **2/70 = 2.9%** |
| `results/frontier-v2.1-local-ollama-14b-n5.jsonl` | 108 | 0/5 ×48 · **1/5 ×1** · 5/5 ×59 | **1/108 = 0.9%** |

All-or-nothing (0/5 or 5/5) is the signature of a deterministic computation repeated
N times — not of sampling.

### 9.2 Root cause — two pinned values conspire

- **`decoding.temperature: 0.0`** → greedy decoding: no sampling, one canonical output.
- **`decoding.seed: 42`**, and **`trial_idx` never reaches the seed.** In `harness/runner.py`
  the trial index is used only for the resume key and the row label; it is never passed to
  the client or backend. Every trial therefore executes the *same* deterministic call.

So **N was not drawing samples from the model's output distribution — it re-ran one
computation N times.** The residual ~1–3% of split cells is *hardware* nondeterminism
(GPU scheduling, non-associative floating-point reduction) occasionally flipping a token
early in the reasoning chain — not model variance.

### 9.3 Why this voids the premise — and the precedent we missed

Pre-registration **S2** rests on the swarm aggregating **independent samples**. The
Amendment Log entry of **2026-07-01** already diagnosed this exact failure *at the peer
level*:

> "Under the pinned temperature 0.0, a single shared seed makes all three peers
> deterministically identical, collapsing the vote and voiding the 'independent samples'
> premise the hypothesis rests on."

and fixed it with `swarm.peer_seed_strategy: offset` (peer *i* draws with `seed + i`).
**The identical reasoning applies across trials — and was never applied.** N=5 over trials
is the same violation the swarm fix repaired over peers. That amendment even anticipated
the alternative now adopted: *"revisit if the advisor prefers temp>0 with a shared seed as
the diversity source instead."*

### 9.4 Consequence for existing data

- Every **N>1** run to date (calibrations, Shadow, M5 Max, HPC) contains N-fold *duplicated*
  trials, not independent samples. Any variance, error bar, or CI derived from them is
  invalid — it quantifies floating-point jitter, not model variability.
- Point estimates are **not** wrong, merely N-fold redundant: **N=1 carries ~97–99% of the
  information of N=5 at 1/5 the compute.** (This is why the M4 cells were run at N=1 with
  no measurable loss, and why the ~5-day M4 N=5 job would have spent ~4 days re-confirming
  trial 1.)
- It also explains a previously puzzling asymmetry: **within** a box, N=5 is flat
  (deterministic), while **across** boxes N=1 diverges (M4 50% vs Shadow 25% on math) —
  different accelerators take different floating-point paths, same-box reruns do not.

### 9.5 The fix

Both knobs are **pinned scientific parameters**, so this is a pre-registration amendment,
not a code tweak — and it changes `config_hash`, which is the point: new data is explicitly
marked as a different configuration rather than silently mixed with the old.

1. **Per-trial seed offset** — `seed = base_seed + trial_idx`, mirroring the existing peer
   offset, so each trial is a distinct draw.
2. **Temperature > 0** — restores genuine sampling so N measures the model's actual output
   variability (the thing the pre-registration assumes N is measuring).

**All trial data is regenerated under the amended config.** Prior runs are retained as the
deterministic-N archive/baseline — they remain valid as *point estimates*, and are the
evidence for this section.

### 9.6 Methodological takeaway (for the paper)

A pinned "reproducibility" setting (temp 0 + fixed seed) silently **defeated the purpose of
replication**: the study was paying 5× compute for a number that could not vary. The lesson
generalizes beyond this harness — *if your design pins determinism, N is a cost multiplier,
not a statistic.* Determinism and replication are in direct tension; a design must choose
which one N is for, and state it.

### 9.7 Fix validated empirically (2026-07-15, M4 / Ollama / deepseek-r1:14b)

First run under the amended config (`temperature 0.6`, `trials.seed_strategy: offset`),
monolithic, N=5:

| task | outcomes across the 5 trials | trial seeds | result |
|---|---|---|---|
| `fx2-hop-001` | True, **False**, True, **False**, True | 1042, 2042, 3042, 4042, 5042 | **3/5 — genuine split** |
| `fx2-mathA-001` | True ×5 | 1042 … 5042 | 5/5 (a genuinely easy item) |

**N now measures something.** Under the old config the split rate across two full N=5
datasets was **2/70 (2.9%)** and **1/108 (0.9%)** — essentially all-or-nothing. Under the
amended config a borderline item immediately produced a **3/5** split, i.e. the model's
real output distribution, which is what the pre-registration assumes N is sampling.
(A 5/5 item is not a failure of the fix: distinct seeds were used — see the seed column —
the item is simply easy enough that every draw succeeds.)

Also confirmed on the same rows: **GPU power telemetry is live on Apple M4**
(`gpu_power_w: 12.5`, `avg_gpu_util_pct: 89.6`) using the *unmodified* reader written for
the M5 — `powermetrics --samplers gpu_power` emits the same `GPU Power: N mW` format on
both chips, so no chip-specific parser was needed; only the one-time sudoers grant
(`scripts/setup_m5_power.sh`, which is misnamed — it is chip-agnostic).
