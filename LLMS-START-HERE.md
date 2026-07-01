# LLMS START HERE

Last updated: 2026-07-01
Project: ITCS 6881 Independent Study (Summer 2026)
Student: Eric Medlock
Advisor: Dr. Jinzhen Wang

## Executive Summary
This project is a controlled benchmarking study comparing three LLM system architectures under the same tasks and model settings:
- Monolithic backend (single-shot call)
- Agentic backend (sequential multi-agent loop)
- Swarm backend (parallel peer-to-peer agents)

Each backend is tested in two environments:
- Local dual RTX 3090 setup
- Azure GPU VM

Core goal: determine when each architecture wins or loses on accuracy, latency, token usage, cost, and hardware footprint.

## What The Project Is Building
One unified benchmark harness that calls a shared backend interface so every condition is comparable.

Six conditions are planned:
- L-M: Local Monolithic
- L-A: Local Agentic
- L-S: Local Swarm
- C-M: Cloud Monolithic
- C-A: Cloud Agentic
- C-S: Cloud Swarm

Scientific control principles used throughout the docs:
- Same model family and pinned model tag across all conditions
- Frozen prompts and frozen benchmark task set
- Repeated trials per task for variance estimation
- Telemetry captured externally by the harness (not self-reported by backends)

## Intended Deliverables
1. Working prototype with shared interface and all three backends.
2. Reproducible benchmark dataset and telemetry outputs.
3. Final academic paper with methods, results, and validity discussion.

## Current Project State (as documented)
Overall status appears to be late Phase 0 (planning and lock-in), not execution.

What is complete:
- Scope and architecture documentation is strong and detailed.
- Reproducibility strategy is well-defined.
- Literature package is substantial (15 verified papers in 2023-2025 range).
- Benchmarking and telemetry schemas are clearly planned.

What is not complete yet:
- No experiment sessions logged yet.
- Results and analysis tables are still templates.
- Several core lock-in decisions are still marked pending.
- Weekly log shows early progress but no later execution updates.

## Most Important Open Decisions
These appear to be the blockers to begin true implementation and data collection:
- Final approval of three-way scope (Monolithic vs Agentic vs Swarm)
- Final topology choice for Agentic backend
- Final topology choice for Swarm backend
- Framework selection (agentic and swarm)
- Exact model tag and quantization
- Success metric definition by task type
- Trial count N per task-condition
- Final paper format and hard deadline
- Hypothesis pre-registration (must happen before data collection)

## Literature Findings Snapshot
The literature notes support the project direction and identify a gap:
- Strong prior evidence exists that agentic methods can outperform monolithic methods on complex tasks.
- Very little controlled work directly compares true swarm architecture against both monolithic and agentic under identical conditions.
- Many prior studies under-report cost and hardware telemetry, which this project explicitly plans to measure.

This means the proposed three-way controlled comparison is a legitimate and meaningful contribution if executed as documented.

## Suggested Immediate Sequence (Practical)
1. Complete advisor lock-in meeting outcomes in the decision files.
2. Pre-register one hypothesis immediately after decision confirmation.
3. Pin model and framework versions in config and requirements.
4. Build the shared interface and monolithic backend first.
5. Add agentic and swarm backends using identical output schema.
6. Run pilot trials (small N) across all six conditions.
7. Validate telemetry integrity before scaling trial counts.
8. Start full runs only after prompt/task freeze is committed.

## Quick Orientation By Folder
- 01 - Overview: scope, hypothesis options, grading targets.
- 02 - Work Plan: timeline, weekly status, meeting notes.
- 03 - System Design: architecture and backend designs.
- 04 - Infrastructure: local and Azure setup guidance.
- 05 - Models & Frameworks: candidate model/framework decisions.
- 06 - Benchmarking: protocol, benchmark subsets, telemetry schema.
- 07 - Literature Review: verified paper notes and dashboard.
- 08 - Results: run log and analysis templates.
- 09 - Paper: final report outline.
- 10 - Admin: lock-in checklist and decision tracker.

## Bottom Line
The project is well-designed on paper and ready to transition from planning to implementation, but only after a small set of advisor-critical lock-in decisions are finalized and documented.
