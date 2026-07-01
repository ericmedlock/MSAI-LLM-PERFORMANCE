"""Task loader validates the frozen manifest."""

from __future__ import annotations

import json

import pytest

from harness.task_loader import load_tasks
from tests.conftest import ROOT


def test_loads_frozen_tasks_evenly_across_domains():
    tasks = load_tasks(ROOT / "tasks" / "manifest.json")
    assert len(tasks) == 15
    domains = [t.domain for t in tasks]
    assert domains.count("gsm8k") == 5
    assert domains.count("humaneval") == 5
    assert domains.count("hotpotqa") == 5


def test_humaneval_tasks_carry_grading_payload():
    tasks = load_tasks(ROOT / "tasks" / "manifest.json")
    for t in tasks:
        if t.domain == "humaneval":
            assert "entry_point" in t.grading and "test" in t.grading
        else:
            assert t.answer


def _write(tmp_path, tasks):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    return p


def test_duplicate_task_id_rejected(tmp_path):
    m = _write(
        tmp_path,
        [
            {"task_id": "x", "domain": "gsm8k", "prompt": "p", "answer": "1"},
            {"task_id": "x", "domain": "gsm8k", "prompt": "p", "answer": "2"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(m)


def test_unknown_domain_rejected(tmp_path):
    m = _write(tmp_path, [{"task_id": "x", "domain": "mmlu", "prompt": "p", "answer": "1"}])
    with pytest.raises(ValueError, match="unknown domain"):
        load_tasks(m)


def test_missing_answer_rejected(tmp_path):
    m = _write(tmp_path, [{"task_id": "x", "domain": "gsm8k", "prompt": "p"}])
    with pytest.raises(ValueError, match="needs a non-empty"):
        load_tasks(m)
