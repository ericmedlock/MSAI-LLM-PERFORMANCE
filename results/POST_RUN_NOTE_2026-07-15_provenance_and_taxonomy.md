# Post-run note — 2026-07-15: sus-item resolutions (provenance, error taxonomy, floored item)

Resolves the three open items flagged during the 2026-07-14 agentic 2.0 / HPC analysis
(vault: Experiment Run Log, "Sus — look harder before the paper").

## 1. Stale pre-fix rows in the local confirmatory cell — RESOLVED: footnote, do NOT re-run

**Finding.** The 10 strict-agentic rows for `fx2-mathA-001` / `fx2-mathA-002` in
`results/frontier-v2.1-local-ollama-14b-n5.jsonl` have EMPTY final answers. An empty
final candidate should be impossible after the 2026-07-12 thinking-fallback client fix
(empty `content` falls back to `message.thinking`). Conclusion: those rows were produced
by the pre-fix client and preserved by the row-level resumable runner — the committed
540-row cell mixes pre-fix and post-fix client behavior.

**Decision: footnote, not re-run.** Rationale:
- The cell is committed, pinned, confirmatory data; mutating it breaks the append-only
  audit trail. Re-running 10 rows on the 2026-07-15 stack would create a *second*
  provenance mix inside the same file (170 old + 10 new rows).
- The affected failure mode (strict-parse false revision → empty answer) is fully
  characterized, and the **agentic 2.0 cell** (`frontier-v2.1-local-agentic20-14b-n5.jsonl`,
  run entirely post-fix) supersedes it: 0 empty answers, 0 format errors, and the live
  outcome matched the pre-declared counterfactual exactly.
- Impact bound: ≤10/180 rows (≤2/36 tasks) in ONE backend of one cell; the direction is
  known (both tasks graded fail; mathA-001 recovers to 5/5 under 2.0).

**Paper footnote text (draft):** "Ten agentic rows in the local cell predate a
parsing-only client fix (2026-07-12) and carry empty final answers; the agentic 2.0
re-run of the full backend (identical pinned decoding) supersedes them and is used for
all agentic-architecture conclusions."

## 2. `tool_error` taxonomy contamination — RESOLVED: grader fix (category-only)

**Finding.** `grade_humaneval` classified any non-AssertionError crash as `tool_error`.
When budget exhaustion makes the thinking-fallback return raw chain-of-thought prose as
the answer, `extract_code` yields prose → SyntaxError → `tool_error`. Same task on HPC
produced real (wrong) code → `reasoning_error`. Error categories were therefore not
comparable across environments (e.g. `fx21-code-005`: 5× `tool_error` local vs 5×
`reasoning_error` HPC).

**Fix (harness/graders.py, 2026-07-15):** SyntaxError/IndentationError in the candidate
program now grades `format_error` (the answer is not valid Python — an answer-format
failure); other non-assertion crashes remain `tool_error`. **Category-only change:
`correct` is False on every affected path — no accuracy number moves.** Tests updated
(145 passed). Existing committed rows are NOT rewritten; analyses of historical files
should treat local `tool_error` rows with prose answers as budget/format failures
(known instances: `fx21-code-005` ×5 in each of the three local backend cells,
`fx21-code-002` ×1 in swarm 2.0).

## 3. `fx2-mathA-009` floored budget-burner — RESOLVED: keep, flag as floored

0/5 on every backend in every environment (local, HPC; strict and lenient agentic;
swarm 1.0 and 2.0) at 495–500 s/row local and 741 s/row HPC, always hitting the
4-action loop ceiling. The item is pre-registered in the frozen v2.1 tier and stays in
the data, but it contributes zero architecture discrimination — analyses of
architecture effects should list it in the floored-item set (precedent: the v1
closed-book multihop domain), and latency aggregates should note it dominates the
agentic tail (~8% of cell wall-clock).

## Related secondary analysis (same date)

`scripts/swarm_vote_counterfactual.py` — offline re-vote of the swarm 2.0 cell under
alternative vote keys (replay fidelity 180/180): AST code keys merge **zero** of the 55
code ties (peer code is structurally different, similarity ≈0.38 — real diversity, not
formatting); refusal-abstain for multihop buys +0.5 pt (1 flip, `fx2-hop-001`).
Together with the k-voter simulation (5–7 voters < +1 pt), every cheap vote-mechanism
upgrade is exhausted: the binding constraint is the answer distribution itself (the
gold answer never appears in 15 samples on 7/12 math tasks).
