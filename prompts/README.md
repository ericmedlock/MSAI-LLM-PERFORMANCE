# Prompts (version-controlled, frozen after pilot)

All system prompts are stored as files here — never inline in Python — so
they are version-controlled and diffable. Per the pre-registration these
are **frozen after the pilot**; any change afterward is an Amendment Log
entry.

| File | Used by | Role |
|---|---|---|
| `monolithic/system.txt` | Monolithic | single-shot solver |
| `agentic/executor_system.txt` | Agentic | Executor agent |
| `agentic/verifier_system.txt` | Agentic | Verifier agent |
| `swarm/peer_system.txt` | Swarm | independent peer solver |

**By design, the agentic and swarm prompts differ from the monolithic
prompt** (they must, to express the architecture). This difference is
documented, not silently introduced — it is one of the things the study
measures. The *task input* appended to these system prompts is identical
across all backends.
