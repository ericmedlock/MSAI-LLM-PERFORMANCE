"""LLM-as-judge post-processing pass (SECONDARY metric).

Runs AFTER benchmarks: reads committed run rows, asks a different-family judge
model to score each answer's quality (0..max_score) and give an independent
correctness verdict, and writes one judge row per run to ``results/judge/``.
The raw benchmark JSONL is never mutated (pre-reg: raw data is read-only), so
the two phases stay cleanly separated and both remain replayable.

Idempotent/resumable: a judge row is keyed by ``run_id``; already-judged runs
are skipped, so a crash mid-pass loses nothing.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from backends.base import Task
from backends.llm_client import LLMClient

_SCORE_RE = re.compile(r"score\s*[:=]\s*(-?\d+)", re.IGNORECASE)
_VERDICT_RE = re.compile(r"verdict\s*[:=]\s*(correct|incorrect)", re.IGNORECASE)
_REASON_RE = re.compile(r"reason\s*[:=]\s*(.+)", re.IGNORECASE)


@dataclass
class JudgeRecord:
    run_id: str
    task_id: str
    backend: str
    environment: str
    judge_model: str
    judge_score: Optional[int]
    judge_max_score: int
    judge_correct: Optional[bool]
    judge_reason: str
    parse_ok: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def parse_judgment(text: str, max_score: int) -> tuple[Optional[int], Optional[bool], str, bool]:
    """Parse the judge's structured reply. Returns
    ``(score, correct, reason, parse_ok)``; score is clamped to [0, max_score]."""
    score_m = _SCORE_RE.search(text or "")
    verdict_m = _VERDICT_RE.search(text or "")
    reason_m = _REASON_RE.search(text or "")

    score: Optional[int] = None
    if score_m:
        score = max(0, min(max_score, int(score_m.group(1))))
    correct = None
    if verdict_m:
        correct = verdict_m.group(1).lower() == "correct"
    reason = reason_m.group(1).strip() if reason_m else ""
    parse_ok = score is not None and correct is not None
    return score, correct, reason, parse_ok


def build_judge_user_prompt(task: Optional[Task], candidate_answer: str) -> str:
    ref = ""
    question = ""
    if task is not None:
        question = task.prompt
        if task.answer:
            ref = f"\n\nREFERENCE (ground truth):\n{task.answer}"
        elif task.domain == "humaneval":
            ref = "\n\nREFERENCE: correctness is defined by hidden unit tests."
    return f"TASK:\n{question}{ref}\n\nANSWER (candidate):\n{candidate_answer}"


def completed_run_ids(path: str | Path) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    ids: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["run_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def judge_records(
    run_rows: list[dict],
    *,
    client: LLMClient,
    tasks_by_id: dict[str, Task],
    judge_system: str,
    judge_model: str,
    max_score: int,
    output_path: str | Path,
    append: Callable[[str, "JudgeRecord"], None] | None = None,
) -> int:
    """Judge every un-judged run row; append one JudgeRecord each. Returns the
    count of newly written judge rows."""
    append = append or _append_judge
    done = completed_run_ids(output_path)
    written = 0
    for row in run_rows:
        run_id = row.get("run_id")
        if not run_id or run_id in done:
            continue
        task = tasks_by_id.get(row.get("task_id"))
        user = build_judge_user_prompt(task, row.get("answer", ""))
        resp = client.chat(judge_system, user)
        score, correct, reason, parse_ok = parse_judgment(resp.text, max_score)
        record = JudgeRecord(
            run_id=run_id,
            task_id=row.get("task_id", ""),
            backend=row.get("backend", ""),
            environment=row.get("environment", ""),
            judge_model=judge_model,
            judge_score=score,
            judge_max_score=max_score,
            judge_correct=correct,
            judge_reason=reason,
            parse_ok=parse_ok,
        )
        append(str(output_path), record)
        done.add(run_id)
        written += 1
    return written


def _append_judge(path: str, record: JudgeRecord) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(record.to_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    import argparse
    import glob

    from backends.factory import build_judge_client
    from harness.config import load_config, load_dotenv
    from harness.task_loader import load_tasks

    parser = argparse.ArgumentParser(prog="harness.judge", description=__doc__)
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--results", default="results/*.jsonl", help="run rows to judge")
    parser.add_argument("--output", help="judge output JSONL (default: results/judge/<env>.jsonl)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    judge = config.judge.resolved()
    judge_system = Path(config.judge.prompt_file).read_text(encoding="utf-8").strip()
    tasks_by_id = {t.task_id: t for t in load_tasks(config.tasks_manifest)}

    paths = [p for p in sorted(glob.glob(args.results)) if "/judge/" not in p]
    rows: list[dict] = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    env_key = rows[0]["environment"] if rows else config.active_environment
    output = args.output or str(Path(config.results_dir) / "judge" / f"{env_key}.jsonl")

    print(f"Judge model : {judge.model} ({judge.provider} @ {judge.base_url})")
    print(f"Run rows    : {len(rows)} from {len(paths)} file(s)")
    print(f"Output      : {output}")
    if args.dry_run:
        print("\n[dry-run] not calling the judge.")
        return 0

    client = build_judge_client(config)
    written = judge_records(
        rows,
        client=client,
        tasks_by_id=tasks_by_id,
        judge_system=judge_system,
        judge_model=judge.model,
        max_score=config.judge.max_score,
        output_path=output,
    )
    print(f"\nDone. Wrote {written} new judgment(s); {len(rows) - written} already judged.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
