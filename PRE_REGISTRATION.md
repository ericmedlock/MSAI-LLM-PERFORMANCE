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
Date Change Rationale
— — —
5