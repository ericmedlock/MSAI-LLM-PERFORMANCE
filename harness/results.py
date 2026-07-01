"""Per-run telemetry rows: one JSON object per line (JSONL).

Design goals:
- **Replayable**: every figure in the paper can be regenerated from these
  rows alone (raw data committed to git).
- **Crash-safe**: each row is flushed and ``fsync``-ed, so a crash mid-run
  never corrupts earlier rows.
- **Resumable/idempotent**: a run is keyed by
  ``(task_id, backend, environment, trial_idx)``. On restart the runner skips
  keys already present, so re-running the command tops up missing rows
  instead of duplicating work.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

RunKey = tuple[str, str, str, int]


@dataclass
class RunRecord:
    # identity / provenance
    run_id: str
    timestamp: str
    backend: str
    environment: str
    task_id: str
    task_domain: str
    trial_idx: int
    model_tag: str
    config_hash: str
    # outcome
    answer: str
    correct: Optional[bool]
    error_category: Optional[str]
    # primary metrics
    latency_s: float
    tokens_in: int
    tokens_out: int
    total_tokens: int
    tokens_per_s: Optional[float]
    action_count: int
    # telemetry + backend extras
    telemetry: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    raw_trace: str = ""

    def key(self) -> RunKey:
        return (self.task_id, self.backend, self.environment, self.trial_idx)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _key_of(row: dict) -> RunKey:
    return (row["task_id"], row["backend"], row["environment"], row["trial_idx"])


def completed_keys(path: str | Path) -> set[RunKey]:
    """Return the set of run keys already recorded (empty if no file yet).

    Tolerates a truncated final line from an earlier crash.
    """
    p = Path(path)
    if not p.exists():
        return set()
    keys: set[RunKey] = set()
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(_key_of(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue  # partial trailing write from a crash; ignore
    return keys


def append_record(path: str | Path, record: RunRecord) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(record.to_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())
