# Stretch Goals / Future Work

Forward-looking ideas beyond the pre-registered study. Not committed; not part
of the frozen design. Recorded so scope creep stays explicit and intentional.

---

## NEXT UP (v2) — planned after the v1 freeze

The current results (tag `data-freeze-2026-07-01`) are the **v1 / LangGraph
baseline**. These two changes define v2; both are pre-registration amendments.

### 1. Migrate orchestration to established frameworks

- **Swarm → OpenAI Swarm**; **Agentic → CrewAI** (replacing the hand-rolled
  LangGraph graphs).
- Why: less bespoke orchestration code; framework-native handoffs/roles.
- **Caveat (keep honest):** framework is a *pinned variable*. v1 (LangGraph) and
  v2 (Swarm/CrewAI) results are **not directly comparable** — framework overhead
  and orchestration semantics differ. Treat v1 as the frozen baseline and report
  v2 as its own set. The shared `Backend` interface, graders, telemetry, judge,
  and analysis layers **carry over unchanged** — only the two backend internals
  are swapped, so this is a contained migration.

### 3. Frontier task tier — DESIGNED, needs calibration + run

Architecture-favoring tasks are now **in scope** (pre-reg Amendment Log,
2026-07-01) and built: `tasks/frontier_manifest.json` + tier support throughout
the harness. See **[docs/TASK_TIERS.md](TASK_TIERS.md)**. Remaining work: run the
calibration procedure (keep items where monolithic single-pass ∈ ~0.4–0.7),
freeze the surviving set, then run all three backends + judge + analyze. This is
what turns "we measured overhead" into "we found where each architecture wins."

### 2. Ensemble swarm (new condition, not a replacement)

Decisions already made with the researcher:

- **Add as a NEW condition** (`ensemble-swarm`); keep the frozen 3-peer
  same-model swarm as the controlled baseline (so the "model held constant"
  comparison stays intact).
- **15 drones = 5 prompt variants × 3 models.**
  - Models: `deepseek-r1-distill-qwen-14b` + a Qwen (e.g. `qwen/qwen3.5-9b`) +
    **`google/gemma-4-e4b`** (Gemma — a genuinely different family; note
    deepseek-distill and qwen are both Qwen-lineage, so the Gemma is what adds
    real diversity).
  - A **front-end LLM generates 5 prompt variants** of the task, instructed to
    **preserve meaning and the required answer** (paraphrasing an objective
    question can otherwise change its answer — the main validity risk).
  - Each of the 5 variants → all 3 models → 15 responses → **majority vote**
    (domain-normalized `vote_key`, fixed tie-break). Deterministic via temp 0 +
    per-drone seed.
- **Feasibility to verify first (gates the design):** can LM Studio hold all 3
  models loaded at once on 48 GB (weights ~18 GB + KV-cache for concurrent
  requests) without eviction/OOM, and serve them concurrently? A probe script
  exists in scratch; run it before committing to a full sweep.
- **Cost warning:** 15 drones × 75 swarm runs ≈ 1,100+ calls, several on the slow
  reasoning model — expect hours and large token counts; consider a reduced task
  subset or N for the first ensemble pass.

---

## Multi-machine (distributed) swarm & agentic runs

Run the parallel/sequential agents across **separate physical machines** instead
of one GPU, each serving the pinned model via its own endpoint (e.g. M5 Max +
M4 Mini + a cloud VM, each running LM Studio/Ollama).

- **Why it matters:** on a single GPU the swarm's 3 peers *share* the device, so
  each peer is slower under contention (documented caveat — real cost of a
  co-located swarm). Putting each peer on its own machine gives **true hardware
  parallelism**, isolating "architecture cost" from "GPU-sharing cost" and
  modeling a realistic distributed-inference deployment.
- **New variable introduced:** inter-machine **network latency** now adds to
  swarm/agentic wall-clock — itself an interesting thing to measure (local GPU
  contention vs network round-trips).
- **Harness changes needed (small — the client layer already abstracts
  endpoints):**
  - config: a **list** of endpoints per environment (not a single `base_url`).
  - swarm: assign peer *i* → endpoint *i* (round-robin if fewer machines than
    peers); agentic: executor and verifier on different hosts.
  - telemetry: record the **host** each agent ran on; aggregate telemetry across
    machines; keep clocks synced (already flagged in the pre-experiment
    checklist) so cross-host latency is trustworthy.
  - reproducibility: pin the same model tag/digest on every machine; verify with
    `env_snapshot.py` per host.
- **Threat to watch:** heterogeneous hardware across machines (e.g. M5 Max vs M4
  Mini) conflates architecture effects with per-host speed differences — either
  use matched machines, or treat host as an explicit factor.

## Other known-not-built items

- **Cloud cell execution** — Azure GPU VM scripts exist but have never been run;
  complete the on-prem-vs-cloud comparison (the second pre-registered
  environment).
- **N → 10 on a pre-declared subset** — pre-reg S8 allows this if time permits
  (log as an amendment).
- **Heavier judge model** — `llama-3.2-3b` is fast/reliable for the verdict but
  noisy on the 0–4 quality scale; a larger different-family judge (e.g. a Gemma
  that loads reliably) would grade quality better.
- **LLM-judge / human eval on open-ended tasks** — current tasks have answer
  keys, so binary auto-grade suffices; a judge or MTurk/Prolific only earns its
  cost on subjective, no-key tasks (summaries, "which answer is better").
- **Model-family generalization** — repeat with a non-Qwen backend to test
  whether findings transfer (pre-reg S12 limitation).
