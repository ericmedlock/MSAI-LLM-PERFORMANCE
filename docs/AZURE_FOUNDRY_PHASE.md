# Azure phase — managed AI services (Azure AI Foundry), NOT a GPU VM

**Status:** PLANNED — next phase, gated on the HPC confirmatory sweep completing.
**Decision date:** 2026-07-13.
**Supersedes:** `docs/AZURE_CLOUD_CELL_RUNBOOK.md` (GPU-VM + Ollama plan, retained as fallback).

## Why the pivot

A `Standard_NC4as_T4_v3` VM running Ollama is just "HPC with a billing meter" — same
self-hosted serving stack on rented CUDA hardware; it adds no new axis to the study.
The replacement uses **Microsoft's managed AI services** (Azure AI Foundry), which:

1. adds a genuinely different comparison — a **managed serving stack** where nothing
   below the API is controllable — instead of a redundant hardware point;
2. gives hands-on practice with the services covered by the **AI-102** exam;
3. produces a "how hard was it to configure" narrative measured honestly (timed setup
   diary + gotcha count) — paper-relevant summary, blog/Substack/YouTube for the rest.

## The central tension (and how we frame it)

The study pins `deepseek-r1-14b-distill-q4_k_m` down to the GGUF sha256. A managed
serverless endpoint breaks that pin by definition: unknown precision (bf16/fp8, not
Q4_K_M), multi-tenant batching, no `num_ctx` control, best-effort-at-most seed support,
no hardware telemetry. **This cell therefore cannot claim "same artifact, different
hardware."** It is framed instead as:

> **Self-hosted pinned artifact vs. managed inference service** — an EXPLORATORY
> environment (like Shadow), entered via the Amendment Log, never a confirmatory cell.

What it measures: accuracy deltas (quantization + serving stack), latency distribution
(network + multi-tenant variance), determinism at temp 0 (expected to fail — that
itself is a finding), and **$/token vs. GPU-hours**.

## Layer 1 — paper-relevant: `azure-foundry` provider

- New environment key in `config/config.yaml` (Amendment Log entry required; it also
  supersedes the pre-registered `cloud` = Azure-VM environment — note that explicitly).
- New client, likely a small subclass of `OpenAICompatibleClient`: Foundry serverless
  endpoints speak OpenAI-compatible `/chat/completions`; differences are auth
  (`api-key` header or Entra ID bearer) and, for Azure-OpenAI-style endpoints, the
  `api-version` query param.
- Harness additions this cell needs:
  - **per-row cost accounting** (tokens × published serverless price);
  - capture the response's served model/version + request-id (the only
    reproducibility anchor when we don't own the weights);
  - hardware telemetry fields explicitly `null` with a documented reason
    (no NVML on someone else's fleet).

### Model choice (verify first — step 1 of execution)

Check whether **DeepSeek-R1-Distill-Qwen-14B** is serverless-deployable in the Foundry
model catalog (historically the distills were managed-compute-only / region-spotty).
Fallback decision, leaning **same-family-bigger**:

| option | pro | con |
|---|---|---|
| **full DeepSeek-R1 serverless** (preferred fallback) | same family — "what does the managed stack do to this family" | bigger model, dearer per token |
| Phi-4-reasoning (~14B) | size-matched, cheap | different family — muddier comparison |

## Layer 2 — AI-102 practice (exploratory / content, never confirmatory)

Each unit is one blog-post-sized deliverable; do them one at a time, after Layer 1:

- **Foundry Agent Service** re-implementation of the agentic backend — "DIY
  Executor+Verifier loop vs. managed agent runtime" (also a paper paragraph).
- **Azure AI Evaluation SDK** as a second judge alongside `harness.judge`.
- **Azure AI Content Safety** post-processing pass over outputs (blog-only).
- All provisioning via **Bicep / az CLI** in a `scripts/setup-azure.sh`, with a
  timed setup diary in `docs/ENGINEERING_LOG.md` style.

## What we deliberately do NOT do

Managed online endpoint with a custom Ollama container (would preserve model parity)
— "provisioning a GPU with extra steps." Keep as the rebuttal option if a reviewer
demands artifact parity in the cloud; `AZURE_CLOUD_CELL_RUNBOOK.md` covers the
even-simpler VM variant.

## Execution sequence (after HPC N=5 lands)

1. Verify Foundry catalog availability + current serverless pricing for the 14B
   distill; pick the model per the fallback table.
2. Amendment Log entry: define `azure-foundry` exploratory environment — what is and
   is not held constant; supersede the `cloud` VM environment.
3. Client + config + tests (mirror `tests/test_integration_lmstudio.py`), cost
   accounting, setup script with timing diary.
4. Run the frozen frontier-v2.1 sweep (start N=1 pilot for cost calibration, then
   decide N).
5. Layer 2 units, one at a time.

## Content pipeline (non-academic output)

Paper gets: the framed comparison + one configuration-effort paragraph.
Blog/Substack/YouTube get: the setup diary, quota/portal gotchas, Agent Service
vs. hand-rolled loop walkthrough, cost breakdown, AI-102 study notes.
