"""Automated, binary graders — one per domain.

No partial credit (pre-reg S7). Each grader returns ``(correct, error_category)``
where ``error_category`` follows the Gupta taxonomy on failure and is ``None``
on success. The same normalization helpers are reused by the swarm's majority
vote so "agreement" means the same thing as "correctness comparison".
"""

from __future__ import annotations

import re
import string
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from backends.base import Task

# Gupta error taxonomy (subset the automated grader can infer)
ERR_REASONING = "reasoning_error"
ERR_FORMAT = "format_error"
ERR_TOOL = "tool_error"
ERR_TIMEOUT = "timeout"


# --------------------------------------------------------------------------- #
# Shared extraction / normalization                                           #
# --------------------------------------------------------------------------- #
_NUMBER_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")


def extract_final_number(text: str) -> Optional[str]:
    """Return the last number in ``text`` as a canonical numeric string.

    Strips ``$`` and thousands separators; normalizes ``5.0`` -> ``5``.
    """
    matches = _NUMBER_RE.findall(text or "")
    if not matches:
        return None
    raw = matches[-1].replace("$", "").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value.is_integer():
        return str(int(value))
    return repr(value)


_ARTICLES = {"a", "an", "the"}


def normalize_text(text: str) -> str:
    """SQuAD/HotpotQA-style normalization: lowercase, strip punctuation,
    drop articles, collapse whitespace."""
    text = (text or "").lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    tokens = [t for t in text.split() if t not in _ARTICLES]
    return " ".join(tokens)


_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """Pull the first fenced code block; fall back to the raw text."""
    match = _CODE_BLOCK_RE.search(text or "")
    return (match.group(1) if match else (text or "")).strip()


# --------------------------------------------------------------------------- #
# Per-domain graders                                                          #
# --------------------------------------------------------------------------- #
def grade_gsm8k(task: Task, answer: str) -> tuple[bool, Optional[str]]:
    predicted = extract_final_number(answer)
    if predicted is None:
        return False, ERR_FORMAT
    expected = extract_final_number(task.answer or "")
    return (predicted == expected), (None if predicted == expected else ERR_REASONING)


def grade_hotpotqa(task: Task, answer: str) -> tuple[bool, Optional[str]]:
    gold = normalize_text(task.answer or "")
    pred = normalize_text(answer)
    if not pred:
        return False, ERR_FORMAT
    # Exact normalized match, or gold appearing as a contiguous span in the
    # prediction (models often wrap the entity in a sentence).
    ok = pred == gold or f" {gold} " in f" {pred} "
    return ok, (None if ok else ERR_REASONING)


def grade_humaneval(
    task: Task, answer: str, *, timeout_s: float = 15.0
) -> tuple[bool, Optional[str]]:
    entry_point = task.grading["entry_point"]
    test_src = task.grading["test"]
    candidate = extract_code(answer)
    if entry_point not in candidate:
        return False, ERR_FORMAT

    program = (
        candidate
        + "\n\n"
        + test_src
        + f"\n\ncheck({entry_point})\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "prog.py"
        script.write_text(program, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return False, ERR_TIMEOUT
    if proc.returncode == 0:
        return True, None
    # AssertionError => wrong logic; anything else => it did not even run.
    stderr = proc.stderr or ""
    return False, (ERR_REASONING if "AssertionError" in stderr else ERR_TOOL)


_GRADERS = {
    "gsm8k": grade_gsm8k,
    "hotpotqa": grade_hotpotqa,
    "humaneval": grade_humaneval,
}


def grade(task: Task, answer: str) -> tuple[bool, Optional[str]]:
    """Dispatch to the domain grader. Returns ``(correct, error_category)``."""
    try:
        grader = _GRADERS[task.domain]
    except KeyError:  # pragma: no cover - guarded at load time
        raise ValueError(f"no grader for domain {task.domain!r}")
    return grader(task, answer)


def vote_key(domain: str, answer: str) -> str:
    """Canonical key used to decide swarm peer agreement, per domain.

    Uses the same normalization as grading so a majority vote is measuring
    the same notion of "same answer" that grading measures.
    """
    if domain == "gsm8k":
        return extract_final_number(answer) or ""
    if domain == "hotpotqa":
        return normalize_text(answer)
    if domain == "humaneval":
        return extract_code(answer)
    return (answer or "").strip()
