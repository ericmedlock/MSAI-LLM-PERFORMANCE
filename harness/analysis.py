"""Analysis over committed telemetry rows.

Implements the pre-registration's declared reporting (S9): mean +/- std for
every metric (never a single run), accuracy-vs-latency and accuracy-vs-tokens
Pareto frontiers, and an error distribution by architecture. Pure functions
over the JSONL rows so figures are fully replayable from committed data.

Stdlib only (``statistics``) -- no numpy/pandas dependency. Optional PNG charts
are produced by :func:`write_charts` iff matplotlib is installed.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


# --------------------------------------------------------------------------- #
# Loading                                                                     #
# --------------------------------------------------------------------------- #
def load_records(paths: Iterable[str | Path]) -> list[dict]:
    """Load and concatenate JSONL rows from one or more result files."""
    records: list[dict] = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# --------------------------------------------------------------------------- #
# Stats                                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Stat:
    n: int
    mean: float
    std: float  # sample stdev; 0.0 when n < 2

    def fmt(self, unit: str = "", places: int = 1) -> str:
        return f"{self.mean:.{places}f}±{self.std:.{places}f}{unit}"


def stat(values: Iterable[Optional[float]]) -> Stat:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return Stat(0, 0.0, 0.0)
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return Stat(len(vals), mean, std)


@dataclass
class CellSummary:
    """Aggregated metrics for one group of runs (e.g. one backend)."""

    keys: dict
    n: int
    accuracy: float                 # fraction correct in [0,1]
    latency_s: Stat
    total_tokens: Stat
    tokens_out: Stat
    action_count: Stat
    tokens_per_s: Stat
    peak_ram_mb: Stat = field(default_factory=lambda: Stat(0, 0.0, 0.0))

    def label(self, order: tuple[str, ...]) -> str:
        return " / ".join(str(self.keys[k]) for k in order if k in self.keys)


def summarize(records: list[dict], group_keys: tuple[str, ...]) -> list[CellSummary]:
    """Group ``records`` by ``group_keys`` and compute mean+/-std per metric.

    Groups are returned sorted by their key tuple for deterministic output.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = tuple(r.get(k) for k in group_keys)
        groups.setdefault(key, []).append(r)

    summaries: list[CellSummary] = []
    for key, rows in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        n = len(rows)
        correct = sum(1 for r in rows if r.get("correct") is True)
        summaries.append(
            CellSummary(
                keys=dict(zip(group_keys, key)),
                n=n,
                accuracy=correct / n if n else 0.0,
                latency_s=stat(r.get("latency_s") for r in rows),
                total_tokens=stat(r.get("total_tokens") for r in rows),
                tokens_out=stat(r.get("tokens_out") for r in rows),
                action_count=stat(r.get("action_count") for r in rows),
                tokens_per_s=stat(r.get("tokens_per_s") for r in rows),
                peak_ram_mb=stat((r.get("telemetry") or {}).get("peak_ram_mb") for r in rows),
            )
        )
    return summaries


# --------------------------------------------------------------------------- #
# Pareto frontier                                                             #
# --------------------------------------------------------------------------- #
def pareto_frontier(
    points: list[dict],
    x_key: str,
    y_key: str,
    *,
    minimize_x: bool = True,
    maximize_y: bool = True,
) -> list[dict]:
    """Return the non-dominated subset of ``points``.

    Default objective: minimize x (cost/latency), maximize y (accuracy). A
    point is dominated if another is at least as good on both axes and
    strictly better on at least one.
    """
    frontier: list[dict] = []
    for p in points:
        dominated = False
        for q in points:
            if q is p:
                continue
            better_x = q[x_key] <= p[x_key] if minimize_x else q[x_key] >= p[x_key]
            better_y = q[y_key] >= p[y_key] if maximize_y else q[y_key] <= p[y_key]
            strict = q[x_key] != p[x_key] or q[y_key] != p[y_key]
            if better_x and better_y and strict:
                dominated = True
                break
        if not dominated:
            frontier.append(p)
    return frontier


# --------------------------------------------------------------------------- #
# Error distribution                                                          #
# --------------------------------------------------------------------------- #
def error_distribution(records: list[dict], group_key: str = "backend") -> dict[str, dict[str, int]]:
    """Count error categories per group (only failed runs contribute)."""
    dist: dict[str, dict[str, int]] = {}
    for r in records:
        if r.get("correct") is True:
            continue
        group = str(r.get(group_key))
        cat = r.get("error_category") or "uncategorized"
        dist.setdefault(group, {})
        dist[group][cat] = dist[group].get(cat, 0) + 1
    return dist
