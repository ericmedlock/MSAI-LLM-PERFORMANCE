# Stretch Goals / Future Work

Forward-looking ideas beyond the pre-registered study. Not committed; not part
of the frozen design. Recorded so scope creep stays explicit and intentional.

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
