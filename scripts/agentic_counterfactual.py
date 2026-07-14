"""Agentic false-revision counterfactual re-parse (Amendment Log 2026-07-14).

SECONDARY post-processing analysis over saved traces. The primary metric is
untouched: this script never rewrites result rows. It replays each agentic
row's trace and asks what the row would have scored had the verifier's verdict
been read leniently instead of with the pinned ``startswith("APPROVE")``.

Pre-declared mechanical rule (do not change without a new amendment):
  * Walk the trace in order. At the FIRST verifier turn whose lenient verdict
    is APPROVE, the counterfactual final answer is the candidate that verifier
    evaluated (the most recent executor output before it), graded with the
    pinned grader. Otherwise the recorded outcome is kept.
  * Lenient verdict: scan the verifier's visible text for the standalone
    tokens APPROVE / REVISE; the LAST occurrence decides; neither -> REVISE.

Usage:
  .venv/bin/python scripts/agentic_counterfactual.py \
      results/frontier-v2.1-local-ollama-14b-n5.jsonl \
      results/frontier-v2-shadow-trial-14b.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.graders import grade
from harness.task_loader import load_tasks

MANIFESTS = (
    "tasks/frontier_v2_manifest.json",
    "tasks/frontier_v2_1_manifest.json",
)

_TOKEN = re.compile(r"\b(APPROVE|REVISE)\b")


def lenient_verdict(text: str) -> bool:
    """True iff the LAST standalone APPROVE/REVISE token is APPROVE."""
    hits = _TOKEN.findall(text.upper())
    return bool(hits) and hits[-1] == "APPROVE"


def counterfactual_row(row: dict, task) -> tuple[bool, bool]:
    """Return (pinned_correct, counterfactual_correct) for one agentic row."""
    pinned = bool(row.get("correct"))
    try:
        trace = json.loads(row["raw_trace"])
    except (KeyError, TypeError, ValueError):
        return pinned, pinned  # no usable trace -> keep recorded outcome
    candidate = None
    for step in trace:
        agent = step.get("agent")
        if agent == "executor":
            candidate = step.get("output", "")
        elif agent == "verifier" and candidate is not None:
            if lenient_verdict(step.get("output", "")):
                correct, _ = grade(task, candidate)
                return pinned, bool(correct)
    return pinned, pinned  # no lenient approval anywhere -> keep recorded


def main(paths: list[str]) -> None:
    tasks = {}
    for m in MANIFESTS:
        for t in load_tasks(m):
            # v2 and v2.1 share math/multihop task_ids (identical items);
            # later manifests win, which is correct for shared ids.
            tasks[t.task_id] = t

    for path in paths:
        per_dom = defaultdict(lambda: [0, 0, 0])  # domain -> [n, pinned, cf]
        flips_up = flips_down = 0
        skipped = 0
        for line in open(path):
            row = json.loads(line)
            if row.get("backend") != "agentic":
                continue
            task = tasks.get(row["task_id"])
            if task is None:
                skipped += 1
                continue
            pinned, cf = counterfactual_row(row, task)
            d = per_dom[row["task_domain"]]
            d[0] += 1
            d[1] += int(pinned)
            d[2] += int(cf)
            flips_up += int(cf and not pinned)
            flips_down += int(pinned and not cf)

        env = json.loads(open(path).readline()).get("environment", "?")
        print(f"\n=== {path}  (environment: {env}) ===")
        print(f"{'domain':<10} {'pinned':>12} {'counterfactual':>16} {'delta':>7}")
        tot = [0, 0, 0]
        for dom in ("math", "code", "multihop"):
            if dom not in per_dom:
                continue
            n, p, c = per_dom[dom]
            tot = [tot[0] + n, tot[1] + p, tot[2] + c]
            print(f"{dom:<10} {p:>6}/{n:<3} {p/n:>4.0%} {c:>8}/{n:<3} {c/n:>4.0%} {(c-p)/n:>+7.1%}")
        n, p, c = tot
        if n:
            print(f"{'OVERALL':<10} {p:>6}/{n:<3} {p/n:>4.0%} {c:>8}/{n:<3} {c/n:>4.0%} {(c-p)/n:>+7.1%}")
        print(f"flips: {flips_up} wrong->right, {flips_down} right->wrong"
              + (f" | skipped (unknown task_id): {skipped}" if skipped else ""))


if __name__ == "__main__":
    main(sys.argv[1:] or [
        "results/frontier-v2.1-local-ollama-14b-n5.jsonl",
        "results/frontier-v2-shadow-trial-14b.jsonl",
    ])
