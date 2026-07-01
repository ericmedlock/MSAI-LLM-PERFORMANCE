"""Load the frozen task suite from ``tasks/manifest.json``."""

from __future__ import annotations

import json
from pathlib import Path

from backends.base import Task
from harness.graders import ANSWER_DOMAINS, CODE_DOMAINS

_VALID_DOMAINS = ANSWER_DOMAINS | CODE_DOMAINS
_VALID_TIERS = {"baseline", "frontier"}


def load_tasks(manifest_path: str | Path) -> list[Task]:
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    tasks: list[Task] = []
    seen: set[str] = set()
    for item in data["tasks"]:
        domain = item["domain"]
        if domain not in _VALID_DOMAINS:
            raise ValueError(f"unknown domain {domain!r} in manifest")
        task_id = item["task_id"]
        if task_id in seen:
            raise ValueError(f"duplicate task_id {task_id!r} in manifest")
        seen.add(task_id)
        tier = item.get("tier", "baseline")
        if tier not in _VALID_TIERS:
            raise ValueError(f"task {task_id!r} has invalid tier {tier!r}")
        if domain in CODE_DOMAINS:
            grading = item.get("grading", {})
            if "test" not in grading or "entry_point" not in grading:
                raise ValueError(
                    f"{domain} task {task_id!r} needs grading.test and grading.entry_point"
                )
        elif not item.get("answer"):
            raise ValueError(f"task {task_id!r} ({domain}) needs a non-empty 'answer'")
        tasks.append(
            Task(
                task_id=task_id,
                domain=domain,
                prompt=item["prompt"],
                answer=item.get("answer"),
                grading=item.get("grading", {}),
                source_id=item.get("source_id"),
                tier=tier,
            )
        )
    if not tasks:
        raise ValueError("manifest contains no tasks")
    return tasks
