"""Frontier-tier task suite: loads correctly, and every item is self-consistent
(reference solutions pass their own unit tests; reference answers grade correct).
This catches task-authoring bugs before any model is run."""

from __future__ import annotations

import json

import pytest

from harness.graders import grade
from harness.task_loader import load_tasks
from tests.conftest import ROOT

FRONTIER = ROOT / "tasks" / "frontier_manifest.json"


def test_frontier_manifest_loads_with_tier_and_domains():
    tasks = load_tasks(FRONTIER)
    assert len(tasks) >= 8
    assert all(t.tier == "frontier" for t in tasks)
    assert {t.domain for t in tasks} <= {"math", "code", "multihop"}


def _raw():
    return json.loads(FRONTIER.read_text())["tasks"]


@pytest.mark.parametrize("item", [t for t in _raw() if t["domain"] == "code"],
                         ids=lambda t: t["task_id"])
def test_code_reference_solution_passes_its_own_tests(item):
    # Proves the unit tests are correct: the authored solution must grade CORRECT.
    from backends.base import Task

    task = Task(item["task_id"], "code", item["prompt"], grading=item["grading"])
    answer = f"```python\n{item['reference_solution']}\n```"
    correct, err = grade(task, answer)
    assert correct is True, f"{item['task_id']} reference solution failed grading: {err}"


@pytest.mark.parametrize("item", [t for t in _raw() if t["domain"] in ("math", "multihop")],
                         ids=lambda t: t["task_id"])
def test_answer_items_grade_their_own_reference_answer(item):
    from backends.base import Task

    task = Task(item["task_id"], item["domain"], item["prompt"], answer=item["answer"])
    correct, _ = grade(task, item["answer"])
    assert correct is True, f"{item['task_id']} gold answer does not self-grade"


def test_math_answers_are_integers():
    for item in _raw():
        if item["domain"] == "math":
            assert item["answer"].lstrip("-").isdigit(), item["task_id"]
