# Post-run note — agentic empty-answer / `format_error` (investigate before HPC N=5)

**Raised:** 2026-07-12, during the Shadow PC frontier-v2 trial (N=1, RTX A4500, Ollama `deepseek-r1:14b`).
**Status:** OPEN — do **not** edit frozen files (`config/config.yaml`, `tasks/`, `prompts/`) without a
PRE_REGISTRATION Amendment Log entry. This is a harness/extraction bug hunt, not a science change.

## Symptom

On the N=1 Shadow trial, `monolithic` (14/36) edged `agentic` (12/36). The gap is **not**
statistically meaningful at N=1 (a 2-item swing on 33 comparable items), and the domain
breakdown shows the deficit is **code-specific** — agentic actually *beats* mono on math:

| domain | mono | agentic | swarm |
|--------|------|---------|-------|
| math   | 3/12 | 5/12    | 6/12  |
| code   | 5/12 | 2/12    | 3/12  |
| hop    | 7/10 | 5/9     | 7/9   |

Most of the code deficit is **genuine reasoning loss** — the reason-only verifier (no code
execution in the loop) over-corrects working solutions into broken ones (e.g. `fx2-codeH-008`:
mono's passing `shutil.copy2(src_str, dest_file)` was rewritten by agentic into a failing
`copy2(src_path, dest_path)`). Those rows are `reasoning_error` with complete code blocks; the
grader is behaving correctly. That part is a legitimate finding, not a bug.

## The actual bug to check

**4 items are tagged `format_error` for `agentic` while `monolithic` parsed fine, and in every
one the agentic `answer` field is EMPTY despite thousands of generated tokens:**

| task_id       | agentic tok_out | action_count | agentic answer | mono result      |
|---------------|-----------------|--------------|----------------|------------------|
| fx2-codeH-007 | 9,701           | 2            | (empty)        | reasoning_error  |
| fx2-codeH-011 | 14,007          | 4            | (empty)        | **correct**      |
| fx2-mathA-002 | 11,443          | 2            | (empty)        | **correct**      |
| fx2-mathA-005 | 24,576          | 4            | (empty)        | reasoning_error  |

`fx2-mathA-005` hit **exactly 24576 = 24×1024 tokens** — the max-token ceiling — with the loop's
maximum `action_count=4`. Strong signal that the agentic executor/verifier loop **consumes the
entire token budget across its passes and never emits a parseable final answer**, which the
grader then scores as `format_error` (= automatic fail).

At least 2 of these 4 (`codeH-011`, `mathA-002`) are items monolithic got **right**, so this
empty-answer failure directly and *unfairly* widens the mono-over-agentic gap. Left unfixed it
will bias the N=5 HPC confirmatory run against the agentic architecture.

## Two hypotheses (not mutually exclusive)

1. **Budget exhaustion in the loop.** `max_tokens` / `num_predict` is applied per model call, but
   the agentic loop makes 2–4 calls; on hard items the final answer-emitting call has little/no
   headroom, or the loop terminates on the token cap before a clean final answer is produced.
2. **Final-answer extraction from the multi-turn trace fails.** The extractor that pulls the
   agentic backend's final answer out of its executor/verifier message trace may not find a
   "final answer" line when the last turn is a truncated or verifier-style message, yielding "".

## Suggested investigation (read-only first)

- Pull the full `raw_trace` for these 4 `(task_id, backend='agentic')` rows from
  `results/frontier-v2-shadow-trial-14b.jsonl` and read the last 1–2 turns: is there content the
  extractor should have caught (→ hypothesis 2), or did generation stop mid-thought at the cap
  (→ hypothesis 1)?
- Inspect the agentic final-answer extraction in `backends/agentic.py` (how the last message maps
  to `BackendResult.answer`) and the format grader in `harness/graders.py`.
- Check how `decoding.max_tokens` / `num_ctx` is passed per call in the agentic loop vs monolithic.

## Fix guidance

- If it's extraction (hyp. 2): a harness/extraction fix is safe to make without an amendment —
  it does not change pinned science, only how an already-generated answer is read. Re-run the 4
  cells (runner is resumable) and confirm.
- If it's budget (hyp. 1): changing `max_tokens` or the loop's per-call budget **is** a pinned
  decoding parameter → requires a PRE_REGISTRATION Amendment Log entry and re-running the affected
  cells. Discuss with advisor before touching it.

## Do NOT

- Do not silently bump `max_tokens` or edit prompts to "help" agentic — that contaminates the
  cross-architecture comparison. Any pinned-parameter change is an amendment, logged and applied
  to all cells uniformly.
