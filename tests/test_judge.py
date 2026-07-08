"""LLM-as-judge post-processing: parsing, judging, idempotency, analysis join."""

from __future__ import annotations

import json

from backends.base import Task
from harness.analysis import join_judge, summarize
from harness.judge import (
    build_judge_user_prompt,
    judge_records,
    load_task_index,
    parse_judgment,
)
from tests.conftest import FakeLLMClient


# -- parsing ---------------------------------------------------------------- #
def test_parse_well_formed_judgment():
    score, correct, reason, ok = parse_judgment(
        "SCORE: 4\nVERDICT: CORRECT\nREASON: matches reference", max_score=4
    )
    assert (score, correct, ok) == (4, True, True)
    assert reason == "matches reference"


def test_parse_clamps_and_handles_incorrect():
    score, correct, _, ok = parse_judgment("SCORE: 9\nVERDICT: INCORRECT", max_score=4)
    assert score == 4 and correct is False and ok is True


def test_parse_unparseable_marks_not_ok():
    score, correct, _, ok = parse_judgment("I think it's fine", max_score=4)
    assert score is None and correct is None and ok is False


def test_judge_user_prompt_includes_reference_when_present():
    task = Task("t", "gsm8k", "2+2?", answer="4")
    prompt = build_judge_user_prompt(task, "the answer is 4")
    assert "REFERENCE" in prompt and "4" in prompt and "candidate" in prompt.lower()


# -- manifest loading (baseline + frontier) --------------------------------- #
def test_load_task_index_merges_baseline_and_frontier_manifests():
    # judging spans tiers, so the judge must resolve gold context for BOTH the
    # baseline manifest and the frontier manifest (the gap this fixes).
    index = load_task_index(["tasks/manifest.json", "tasks/frontier_manifest.json"])
    assert "gsm8k-001" in index          # baseline row resolves
    assert "fm-math-001" in index        # frontier row resolves (previously could not)
    assert index["fm-math-001"].tier == "frontier"


def test_load_task_index_single_manifest_default():
    index = load_task_index(["tasks/manifest.json"])
    assert "gsm8k-001" in index and "fm-math-001" not in index


# -- judging pass ----------------------------------------------------------- #
def _run_row(run_id, backend, task_id="gsm8k-001", answer="72"):
    return {"run_id": run_id, "backend": backend, "task_id": task_id,
            "environment": "local", "answer": answer, "correct": True}


def test_judge_records_writes_one_row_per_run_and_is_idempotent(tmp_path):
    out = tmp_path / "judge" / "local.jsonl"
    rows = [_run_row("r1", "monolithic"), _run_row("r2", "swarm")]
    tasks = {"gsm8k-001": Task("gsm8k-001", "gsm8k", "q", answer="72")}
    client = FakeLLMClient(lambda s, u, seed: "SCORE: 4\nVERDICT: CORRECT\nREASON: ok")

    n1 = judge_records(rows, client=client, tasks_by_id=tasks,
                       judge_system="sys", judge_model="gemma", max_score=4, output_path=out)
    n2 = judge_records(rows, client=client, tasks_by_id=tasks,
                       judge_system="sys", judge_model="gemma", max_score=4, output_path=out)
    assert n1 == 2 and n2 == 0                      # idempotent re-run adds nothing

    written = [json.loads(l) for l in out.read_text().splitlines()]
    assert {w["run_id"] for w in written} == {"r1", "r2"}
    assert all(w["judge_score"] == 4 and w["judge_correct"] is True for w in written)


def test_join_judge_and_summarize_quality_and_agreement():
    records = [
        {"run_id": "r1", "backend": "swarm", "correct": True, "latency_s": 1.0,
         "total_tokens": 10, "tokens_out": 5, "action_count": 3, "tokens_per_s": 5.0},
        {"run_id": "r2", "backend": "swarm", "correct": False, "latency_s": 1.0,
         "total_tokens": 10, "tokens_out": 5, "action_count": 3, "tokens_per_s": 5.0},
    ]
    judge_rows = [
        {"run_id": "r1", "judge_score": 4, "judge_correct": True},   # agrees (both True)
        {"run_id": "r2", "judge_score": 2, "judge_correct": True},   # disagrees (auto False)
    ]
    joined = join_judge(records, judge_rows)
    s = summarize(joined, ("backend",))[0]
    assert round(s.judge_quality.mean, 1) == 3.0
    assert s.judge_correct_rate == 1.0            # judge said correct on both
    assert s.judge_agreement == 0.5               # agrees on r1, not r2
