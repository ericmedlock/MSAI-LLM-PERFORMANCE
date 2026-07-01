"""Graders: binary, per-domain, and reused by swarm voting."""

from __future__ import annotations

from backends.base import Task
from harness.graders import (
    ERR_FORMAT,
    ERR_REASONING,
    ERR_TOOL,
    extract_final_number,
    grade,
    grade_humaneval,
    normalize_text,
    vote_key,
)


# -- gsm8k ------------------------------------------------------------------ #
def test_extract_final_number_handles_currency_commas_and_trailing():
    assert extract_final_number("so the total is $1,234") == "1234"
    assert extract_final_number("first 5 then finally 72") == "72"
    assert extract_final_number("5.0") == "5"
    assert extract_final_number("no digits here") is None


def test_gsm8k_correct_and_incorrect():
    task = Task("t", "gsm8k", "q", answer="72")
    assert grade(task, "... altogether 72") == (True, None)
    ok, err = grade(task, "the answer is 71")
    assert ok is False and err == ERR_REASONING
    ok, err = grade(task, "no number at all")
    assert ok is False and err == ERR_FORMAT


# -- hotpotqa --------------------------------------------------------------- #
def test_normalize_text_strips_articles_punctuation_case():
    assert normalize_text("The Arthur's Magazine!") == "arthurs magazine"


def test_hotpotqa_exact_and_span_match():
    task = Task("t", "hotpotqa", "q", answer="Arthur's Magazine")
    assert grade(task, "Arthur's Magazine")[0] is True
    assert grade(task, "It was Arthur's Magazine, started first.")[0] is True
    assert grade(task, "First for Women")[0] is False


# -- humaneval -------------------------------------------------------------- #
_TASK_CODE = Task(
    "t",
    "humaneval",
    "q",
    grading={
        "entry_point": "add",
        "test": "def check(candidate):\n    assert candidate(2, 3) == 5\n    assert candidate(-1, 1) == 0\n",
    },
)


def test_humaneval_passes_on_correct_code():
    ok, err = grade_humaneval(_TASK_CODE, "```python\ndef add(x, y):\n    return x + y\n```")
    assert ok is True and err is None


def test_humaneval_reasoning_error_on_wrong_logic():
    ok, err = grade_humaneval(_TASK_CODE, "```python\ndef add(x, y):\n    return x - y\n```")
    assert ok is False and err == ERR_REASONING


def test_humaneval_format_error_when_function_absent():
    ok, err = grade_humaneval(_TASK_CODE, "I cannot help with that.")
    assert ok is False and err == ERR_FORMAT


def test_humaneval_tool_error_on_syntax_error():
    ok, err = grade_humaneval(_TASK_CODE, "```python\ndef add(x, y)\n    return x+y\n```")
    assert ok is False and err == ERR_TOOL


# -- vote_key --------------------------------------------------------------- #
def test_vote_key_matches_domain_normalization():
    assert vote_key("gsm8k", "answer: 72") == "72"
    assert vote_key("hotpotqa", "The Delhi") == "delhi"
    assert "return x + y" in vote_key("humaneval", "```python\ndef add(x,y):\n    return x + y\n```")
