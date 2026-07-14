Contents
Pre-Registration — LLM Execution Architecture Benchmark 1
1. Research Question . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 1
2. Hypothesis (pre-registered) . . . . . . . . . . . . . . . . . . . . . . . . . 1
3. Conditions (the six cells) . . . . . . . . . . . . . . . . . . . . . . . . . . . 2
4. Environments . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2
5. Model (pinned) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2
6. Framework & Topologies (pinned) . . . . . . . . . . . . . . . . . . . . . 3
7. Task Suite (pinned) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 3
8. Trials & Scale . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4
9. Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4
10. Analysis Plan (declared before data) . . . . . . . . . . . . . . . . . . . . 4
11. Reproducibility Commitments . . . . . . . . . . . . . . . . . . . . . . . 4
12. Threats to Validity (known at pre-registration) . . . . . . . . . . . . . . 4
Amendment Log . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 5
Pre-Registration — LLM Execution Architecture Bench-
mark
Study: Comparative evaluation of monolithic, agentic, and swarm LLM execution
architectures across on-prem and cloud environments. Researcher: Eric Medlock
(emedlock@charlotte.edu), UNC Charlotte Course: ITCS 6881 — Individual Study in
AI, Robotics, and Gaming (Summer 2026) Advisor: Dr. Jinzhen Wang
Pre-registration timestamp: 2026-07-01 07:31 EDT Status: Decisions locked prior
to any data collection. No runs have been executed as of this timestamp.
This document freezes the study design before data. Any change after this
date must be logged in the Amendment Log (bottom) with a timestamp and
rationale. Decisions were made solo (advisor meeting did not occur); each
is stated with rationale so it can be defended or revised.
1. Research Question
Under what conditions does an agentic or swarm architecture outperform a mono-
lithic single-shot LLM — and how do agentic and swarm compare to each other — in
accuracy, latency, token consumption, and hardware resources, across on-prem and
cloud environments?
2. Hypothesis (pre-registered)
H (Candidate D — task-dependent superiority): Architecture superiority is task-
dependent, not absolute. - Agentic (Executor + Verifier) improves accuracy over
monolithic on tasks that benefit from iterative refinement and self-checking (e.g.,
1
code, multi-step arithmetic), at a token and latency cost. - Swarm (parallel peer vot-
ing) improves accuracy over monolithic on tasks where independent samples can be
aggregated (majority vote), at higher token cost than agentic. - Monolithic remains
the latency- and token-cheapest option and is competitive on simple, single-step tasks.
Directional sub-predictions (for falsification): 1. Token cost ordering: mono-
lithic < agentic < swarm (consistent with Kim et al. multipliers ~1.6x agentic, ~2.0–
2.4x swarm). 2. Latency: monolithic lowest; swarm’s wall-clock may beat agentic if
peers truly run in parallel. 3. Accuracy gains from agentic/swarm shrink or vanish
on the easiest (L1) tasks. 4. Variance (CV) increases from monolithic → agentic →
swarm.
Why D: It does not over-claim any single architecture, and it remains defensible
regardless of which way the data breaks — the paper’s contribution is characterizing
when, not declaring a winner.
3. Conditions (the six cells)
Three architectures × two environments:
L-M Monolithic Local (M5 Max)
L-A Agentic Local (M5 Max)
L-S Swarm Local (M5 Max)
C-M Monolithic Cloud (Azure GPU VM)
C-A Agentic Cloud (Azure GPU VM)
C-S Swarm Cloud (Azure GPU VM)
Code Architecture Environment
The only variables that change across cells are architecture and environment.
Model, quantization, prompts, task inputs, temperature, context window, and max-
tokens are held constant.
4. Environments
• Local (on-prem): Apple M5 Max, 48 GB unified memory, Ollama (Metal back-
end).
• Cloud: Azure GPU VM, Ubuntu, Ollama (CUDA backend), served from commit-
ted provisioning script. Budget cap: $100 student credit; track burn rate.
• Same GGUF model tag + quantization served in both. Apple-Silicon-vs-NVIDIA
is the deliberately varied factor; nothing else differs.
• Deferred to future work (out of scope): M4 Mini, Shadow Tech Pro, School
HPC, Google Colab Pro. Named here so scope creep is explicit.
5. Model (pinned)
• Primary: DeepSeek-R1 14B distill, quantization Q4_K_M, served via Ollama
with a pinned model tag/digest recorded in config.yaml.
2
• Decoding: temperature 0.0, fixed context window, fixed max output tokens (val-
ues pinned in config).
• Known tension (flagged, not hidden): DeepSeek-R1 officially recommends
temp ~0.6; the protocol pins 0.0 for determinism. If the pilot shows pathological
behavior (loops, empty reasoning) at 0.0, the pre-approved fallback is Llama 3.1
8B Instruct (Q4_K_M), applied identically to all six cells. Switching models is
an all-or-nothing amendment logged below — never per-cell.
6. Framework & Topologies (pinned)
• Framework: LangGraph (pinned version in requirements.txt). Chosen because
one framework can express both the sequential agentic loop and the parallel,
controller-free swarm.
• Monolithic: one prompt in, one response out. No loop, no delegation.
• Agentic: Executor + Verifier, max 2 loops (Abou Ali: diminishing returns after
2). Sequential, central orchestration.
• Swarm: 3 peer agents, run in parallel, no central controller, outputs aggre-
gated by majority vote (ties broken by a fixed rule recorded in config).
• Agentic and swarm use role-specific system prompts that differ from monolithic.
This difference is documented, not silently introduced — all prompts are
version-controlled and frozen after pilot.
7. Task Suite (pinned)
To meet the timeline and satisfy the “replicate first” mandate, tasks are drawn from
published benchmarks with objective, automated grading rather than hand-
authored. This removes the human-validation bottleneck and improves reproducibil-
ity.
Domain Source benchmark # items Grader
Arithmetic
reasoning
GSM8K 3 Exact
Code HumanEval 3 Unit-test
Multi-hop
retrieval
HotpotQA (or GAIA L1/L2
subset)
numeric
match
pass/fail
3 Exact /
normalized
string match
• Total: 9 fixed items. Exact item IDs are frozen in tasks/manifest.json and never
changed after pilot.
• Grading is fully automated and binary (correct/incorrect). No partial credit.
• Item selection is recorded (IDs + reason) so the subset is reproducible and not
cherry-picked post hoc.
3
8. Trials & Scale
• N = 5 independent runs per (task × architecture × environment).
• Total runs: 9 tasks × 3 architectures × 2 environments × 5 = 270 runs.
• Rationale: N=5 yields a usable mean ± standard deviation to characterize vari-
ance (the rubric rewards discussing variance and surprises), while staying inside
a ~2-week solo window. If time permits, N is increased to 10 on a pre-declared
subset — an amendment, logged below.
9. Metrics
Primary (all cells): accuracy (% correct), wall-clock latency (s), total tokens (input +
output). Secondary: action/loop count (agentic/swarm), peak VRAM / memory, error
category (hallucination, reasoning error, tool error, coordination failure, timeout —
Gupta taxonomy), swarm coordination-token share.
Reporting: mean ± std for every metric (never a single run). Pareto frontiers:
accuracy-vs-latency and accuracy-vs-tokens. Error distribution by architecture.
10. Analysis Plan (declared before data)
• Compare architectures within each environment, and each architecture across
environments.
• Report effect sizes with variance, not just point estimates. No hypothesis fishing:
only the sub-predictions in §2 are confirmatory; anything else found is labeled
exploratory.
• Surprises are reported, not smoothed.
11. Reproducibility Commitments
• All prompts version-controlled; frozen after pilot.
• Model tag/digest, quantization, temperature, context, max-tokens pinned in
config.yaml — never hardcoded.
• Pinned requirements.txt; Azure VM provisioned from a committed script; envi-
ronment snapshot recorded.
• Raw per-run telemetry committed (one row per run) so all figures are replayable.
12. Threats to Validity (known at pre-registration)
• Model-family generality: single model; findings may not transfer to other fam-
ilies (future work).
• Small task N (9): limits domain coverage; mitigated by using established,
objectively-graded items.
• temp=0.0 vs R1’s recommended 0.6: may understate R1’s true capability;
fallback declared in §5.
• Metal vs CUDA: environment differences conflate hardware and runtime stack;
this is intended (it is the on-prem-vs-cloud variable) but must be stated as a
limitation on isolating pure “cloud” effects.
4
• Swarm topology choice (3 peers, majority vote): one of many possible
swarm designs; results are specific to it.
Amendment Log
Any deviation from the above after 2026-07-01 07:31 EDT is recorded here with date,
change, and rationale.

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-07-01 (post-lock, pre-data) | Swarm peers draw with a per-peer decoding seed offset: peer *i* uses `seed = base_seed + i` (pinned as `architectures.swarm.peer_seed_strategy: offset` in config.yaml). Monolithic and agentic backends are unaffected and keep the single pinned seed. No runs had been executed at the time of this amendment. | S2 pre-registers the swarm as improving accuracy by aggregating **independent samples** via majority vote. Under the pinned temperature 0.0, a single shared seed makes all three peers deterministically identical, collapsing the vote and voiding the "independent samples" premise the hypothesis rests on. Fixed per-peer offsets restore genuine sample diversity while remaining fully reproducible (all seeds fixed and version-controlled). Made solo; revisit if the advisor prefers temp>0 with a shared seed as the diversity source instead. Toggle back with `peer_seed_strategy: same`. |
| 2026-07-01 (post-lock, pilot) | Raised pinned `decoding.max_tokens` from **2048 → 6144** (held constant across all cells). | The first judged pilot scored 0% for every architecture on the hard code item: DeepSeek-R1's chain-of-thought consumed the full 2048-token budget before emitting any code, so answers were truncated to pure reasoning (`tokens_out == 2048`, no code block → format_error). 2048 is simply too small an output budget for a reasoning model on code. 6144 is applied identically to all cells, so within-comparison fairness is preserved; results collected before this entry used 2048 and carry the earlier `config_hash` (a full re-run at 6144 precedes any freeze). Reasoning models also need LM Studio's loaded context ≥ this budget + prompt. |
| 2026-07-01 (post-lock, pre-v2) | Added a **frontier task tier** to §7 scope: a second class of tasks selected to be *architecture-favoring* (harder, near the pinned model's capability edge), kept objectively auto-graded (numeric / unit-test / normalized-string). Candidate items in `tasks/frontier_manifest.json` (`tier: frontier`); the frozen v1 suite is now the **baseline** tier and is unchanged. See `docs/TASK_TIERS.md`. | The v1 pilot exposed a validity gap: on the baseline suite the pinned model scores ~93–100% single-pass, i.e. **above the ceiling where iteration/voting can help**, so architectures barely differentiate and the study cannot observe the *task-dependent* superiority its own H (§2) predicts. Self-consistency/voting (swarm) only lifts accuracy in the moderate band (~0.4–0.7 single-pass), and agentic self-correction only pays off when single passes make correctable errors. The frontier tier targets that band. Selection criterion is empirical and pre-declared: an item is kept iff monolithic single-pass accuracy ∈ ~[0.4, 0.7] at N≥5 (calibrated before freezing; items outside the band are dropped, not tuned). This adds a task class, changes no v1 result, and is confirmatory only for the pre-declared H under the stated criterion. |
| 2026-07-01 (post-lock) | Added an **LLM-as-judge secondary metric** as a post-processing pass (`harness.judge`), plus **6 additional harder task items** (task suite now 15: 5 per domain). Binary automated grading (S7) remains the **primary** accuracy metric and is unchanged; the judge only adds a graded-quality score (0–4) and an independent correctness opinion, recorded in a separate `results/judge/` file that never mutates the raw run rows. Judge model is a **different family** (Gemma) from the Qwen-based backend to avoid self-preference. | The initial pilot showed accuracy saturating at 100% on easy items, giving no signal to separate architectures; harder items restore variance, and a quality score captures differences the binary grader cannot. Kept strictly secondary/exploratory so the pre-registered confirmatory analysis (S10) is unaffected. Both are reproducible from committed data. |
| 2026-07-08 (correction, judge model) | Formalizing the judge-model swap already recorded in `config/config.yaml`: the LLM-as-judge is **Llama-3.2-3B-Instruct**, not Gemma as written in the entry above. All judged rows in the v1 freeze (`results/judge/local.jsonl`) were produced with Llama-3.2-3B-Instruct. | Gemma loaded/ran too slowly on the M5 Max to be practical for a 225-row judging pass. Llama-3.2 preserves the property the entry above pre-registered — a **different model family** from the Qwen-based backend (no family self-preference). Secondary metric only; primary binary grading unaffected. |
| 2026-07-08 (provenance, task IDs) | Closed the `id_status: PLACEHOLDER_PENDING_FREEZE` gap in `tasks/manifest.json` via `scripts/verify_task_ids.py`, which fetches each claimed upstream source and compares items. Results: 4× `VERIFIED_UPSTREAM_EXACT` (gsm8k-001..003 = GSM8K train[0..2]; hotpotqa-002 = HotpotQA train 5a879ab05542996e4f30887e), 4× `VERIFIED_UPSTREAM_ADAPTED` (humaneval-001..003 = HumanEval/0,/13,/53 with signature/doctests/entry_point exact but docstrings lightly paraphrased at transcription; hotpotqa-001 = HotpotQA train 5a7a06935542990198eaf050 with one added comma), 7× `PROJECT_AUTHORED` ("-style" items with no upstream identity by design). Also corrected the two hotpotqa `source_id` fields, which claimed "dev" but resolve to the **train** split. Additionally recorded the pinned model artifact digest: `DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf` sha256 `4b90205bacb6938e72196dbb84cd2a79987b2f93efc270496832963e8d0f56af` (the `model.digest` config field is filled from this value). | Pre-registration S11 pins model tag/digest and task provenance; both were left as placeholders at freeze time. **No task prompt, answer, or grading was modified** — the suite stays byte-identical to what the frozen 225-run dataset was collected on; only provenance metadata (`id_status`, two `source_id` strings) changed, so no result is affected. The transcription deviations (paraphrased HumanEval docstrings, one comma, dev→train split labels) are disclosed here rather than silently fixed, per the freeze discipline. |
| 2026-07-09 (frontier tier v2 — recalibrated sources) | A full-size system test (deepseek-r1-distill-qwen-32b, 330 runs over the 22-item external frontier candidates, archived at `results/archive/frontier-external-precalib-32b.jsonl`) showed two of three domains outside the pre-declared calibration band: **code (MBPP sanitized) saturated at 120/120 = 100%** and **closed-book multihop (MuSiQue) floored at 5/90 = 6%**, while math (MATH-500 L≥3) landed **in band at 65%**. New candidate set `tasks/frontier_v2_manifest.json` (built by `scripts/build_frontier_v2.py`): code re-sourced to **BigCodeBench v0.1.4** (stdlib-only subset, unittest-graded via the same subprocess grader); multihop re-issued as **MuSiQue WITH supporting passages** (+distractors up to a fixed context-char budget) since MuSiQue's upstream calibration assumes provided context — closed-book, the bottleneck is parametric recall, which no architecture can iterate or vote around; math items carried over unchanged (same task_ids). Every item self-grades through the real grader before inclusion. The selection criterion is **unchanged** from the 2026-07-01 frontier amendment: keep iff monolithic single-pass accuracy ∈ ~[0.4, 0.7] at N≥5 against the pinned model; out-of-band items are dropped, not tuned. Also filled `model.digest` in config.yaml (sha256 recorded in the 2026-07-08 entry); rows before this date carry the earlier config_hash. | The tier exists to occupy the accuracy band where architecture effects are observable; the system test demonstrated empirically that two domains missed that band (ceiling and floor respectively), so keeping them would make the confirmatory tier×architecture analysis uninformative by construction. Sources were swapped under the same pre-declared, empirical criterion — this is re-sourcing, not tuning toward a preferred outcome, and the saturated/floored evidence is preserved and disclosed. GAIA was again considered and rejected for the in-scope tier: it benchmarks tool orchestration (browse/files/code-exec), which the no-tool design deliberately excludes; noted as v2+ future work. |
| 2026-07-09 (calibration rule + round 2) | Round-1 calibration of the v2 candidates against the pinned 14B (monolithic N=5, 180 runs, `results/frontier-v2-calib-14b.jsonl`) showed per-item accuracy is **near-binary** (5/5 or 0/5) under the pinned temp-0.0/fixed-seed decoding — only serving-level nondeterminism produces intermediate rates — so the per-item 0.4–0.7 band in the 2026-07-01 frontier amendment is unsatisfiable as written. **Rule restated at the domain aggregate:** a domain's full candidate list is kept iff its aggregate monolithic accuracy lands in ~[0.4, 0.7]; out-of-band domains are re-sourced whole from a pre-declared harder/easier tier of the same benchmark family and recalibrated. Item-level selection by outcome is prohibited (that would tune the tier toward a preferred result). Round-1 verdicts: multihop (MuSiQue with context) 67% IN BAND -> kept; math (MATH-500 L3-5) 88% and code (BigCodeBench stdlib slice) 89% ABOVE band -> re-sourced to MATH-500 level-5-only (10 items) and BigCodeBench-HARD stdlib-only (12 items), declared here BEFORE their calibration runs. | A frontier tier only serves its purpose (the accuracy band where architecture effects are observable) if the selection rule is feasible under the pinned decoding. The aggregate-level rule preserves the pre-declared, mechanical character of selection while working with near-deterministic runs; keeping whole domains (solved and unsolved items in natural proportion) is exactly what lets the confirmatory analysis ask whether iteration or voting rescues failed items. |
| 2026-07-09 (calibration round 3, math) | Round-2 verdicts at the pinned 14B: **code (BigCodeBench-Hard stdlib-only) 48% IN BAND** -> kept; multihop unchanged (67%, in band); **math (MATH-500 level-5-only) 80% still ABOVE band**. Math re-sources to **AIME 2025** (`math-ai/aime25`, 12 items, integer answers), declared here before its calibration runs. | AIME is the standard next difficulty rung above MATH-500 for this model family (published R1-distill AIME-2025 scores sit near the band), answers are integers by construction (fits the exact-match grader unchanged), and the 2025 contest post-dates the pinned model's training cutoff, removing the contamination concern that MATH-500 carries. Same mechanical whole-domain rule; no item-level selection. |
| 2026-07-09 (FRONTIER TIER FROZEN) | Round-3 verdict: math (AIME 2025) **42% IN BAND**. All three domains now satisfy the domain-aggregate band at the pinned 14B: math 25/60=42%, code (BigCodeBench-Hard) 29/60=48%, multihop (MuSiQue with context) 40/60=67%; tier aggregate 94/180=52%. `tasks/frontier_v2_manifest.json` is frozen (36 items, 12/domain) and immutable; calibration evidence embedded in the manifest and preserved in `results/frontier-v2-calib-14b.jsonl` (350 monolithic runs across 3 rounds). | Freezing before any multi-architecture run preserves the confirmatory character of the upcoming tier x architecture analysis: item selection was completed mechanically, under pre-declared rules, before any agentic/swarm data existed. |
| 2026-07-13 (frontier v2.1 — code re-source after cross-stack drift) | A production-stack calibration check (monolithic N=5 via **Ollama**, the serving stack for all remaining environments; 60 runs, `results/calib-code-ollama-14b.jsonl`) measured the frozen v2 code domain at **21/60 = 35%**, below the [0.4, 0.7] band — versus 48% in the original LM Studio calibration. The cross-stack drift is real (per-item: same 4 items solid, 7 floored). Per the domain-aggregate rule the domain re-sources mechanically: **v2.1 code = deterministic 6+6 mix** of the first-6 validating stdlib-only items from bigcodebench-hard and from plain bigcodebench (hard ids excluded; overlap verified none). Assembled from committed artifacts during an HF datasets-server outage — both halves were originally fetched by the identical first-N-validating rule; full 148-item hard-set exclusion re-verification pending endpoint recovery. Math and multihop carry UNCHANGED (same task_ids). `tasks/frontier_v2_manifest.json` stays immutable; datasets already collected against v2 remain v2 data. v2.1 freezes only if its code domain passes mono N=5 **on the production stack**, declared here before that calibration runs. Additionally adopted as method: **calibration bands are verified on the production serving stack before any multi-architecture sweep** (new reporting guardrail #3). | The tier's validity criterion is band placement on the stack that produces the study data; a domain in band on one stack and at 35% on the production stack fails that criterion in the way that matters. The mixed rung is the mechanical midpoint between the two measured rungs (plain 89% above band, hard 35% below), keeps both sources' first-N-validating selection (no outcome peeking at the item level), and the fallback assembly reuses only artifacts already committed under the same rule. |
| 2026-07-13 (FRONTIER v2.1 FROZEN) | The re-sourced code domain calibrated at **35/60 = 58% IN BAND on the production stack** (6 items solved / 6 unsolved — the mix the tier×architecture analysis needs). All three domains now hold band placement with production-stack evidence: math 42%, code 58%, multihop 67%. `tasks/frontier_v2_1_manifest.json` frozen and immutable (36 items). The confirmatory sweep (3 architectures × N=5) runs on v2.1; datasets previously collected on v2 remain labeled v2. | Freeze completed before any multi-architecture data existed for the re-sourced domain — selection stayed mechanical and confirmatory. |
| 2026-07-14 (agentic false-revision — counterfactual re-parse declared) | Live monitoring of the in-flight local v2.1 sweep (95 agentic rows at discovery) surfaced a protocol-parsing mismatch in the agentic backend: the pinned verifier prompt requires the verdict on the **first line** ("APPROVE or REVISE") and `backends/agentic.py` parses approval as `text.strip().upper().startswith("APPROVE")` — but the reasoning model routinely explains first and verdicts later, and when a verifier turn exhausts `max_tokens` the Ollama `thinking` fallback returns chain-of-thought that can never begin with APPROVE. Verbal approvals are thus consumed as revision requests (**false revisions**), forcing extra loops that burn budget and can replace a correct, approved draft with an empty final answer. Snapshot at discovery: **20/95 agentic rows** carried a false revision on the first verifier turn; in **≥5** the executor draft was correct AND verbally approved, yet the row scored 0 (e.g. fx2-mathA-001: executor 70 = gold, verifier "APPROVE … \boxed{70}", recorded `approved: false`, final answer empty, all 5 trials). **No change to the running system:** prompts, parsing, decoding, and loop cap stay pinned; every environment (v1, Shadow, M4, local, HPC) runs identical code, so the primary metric stays comparable. Declared here — before the sweep completes and before any counterfactual number is computed — as a **SECONDARY post-processing analysis over saved traces**: replay each agentic row's trace; at the **first** verifier turn whose lenient verdict is APPROVE, take the candidate that verifier evaluated as the counterfactual final answer and grade it with the pinned grader; otherwise keep the recorded outcome. Lenient verdict rule (mechanical): scan the verifier's visible text for the standalone tokens APPROVE / REVISE; the **last** occurrence decides; neither present → REVISE. Report pinned and counterfactual agentic accuracy side by side, per domain and per environment. | The pinned run measures the deployed framework as-built; the counterfactual isolates how much of agentic's deficit is **protocol-compliance loss** ("the verifier approved but the framework didn't hear it") versus verifier judgment. The rule is trace-mechanical, fixed before any result exists, uses only already-recorded data and the pinned grader, and touches no frozen machinery mid-study — preserving the confirmatory character of the primary analysis while making the deficit attributable. |

5
