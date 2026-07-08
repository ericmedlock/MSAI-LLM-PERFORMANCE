"""Analysis: stats, Pareto frontier, error distribution, report rendering."""

from __future__ import annotations

import json

from harness.analysis import (
    error_distribution,
    load_records,
    pareto_frontier,
    stat,
    summarize,
)
from harness.report import build_report


def _rec(backend, task, correct, latency, tin=10, tout=20, actions=1, err=None, env="local"):
    return {
        "backend": backend, "task_id": task, "environment": env,
        "model_tag": "deepseek", "correct": correct, "error_category": err,
        "latency_s": latency, "tokens_in": tin, "tokens_out": tout,
        "total_tokens": tin + tout, "tokens_per_s": tout / latency if latency else None,
        "action_count": actions, "telemetry": {"peak_ram_mb": 100.0},
    }


def test_stat_mean_std_and_single_value():
    s = stat([2.0, 4.0, 6.0])
    assert s.n == 3 and round(s.mean, 3) == 4.0 and round(s.std, 3) == 2.0
    one = stat([5.0])
    assert one.n == 1 and one.std == 0.0            # std undefined for n=1 -> 0
    assert stat([None, None]).n == 0                 # all-missing -> empty


def test_summarize_groups_and_accuracy():
    records = [
        _rec("monolithic", "t1", True, 2.0),
        _rec("monolithic", "t1", False, 4.0),
        _rec("swarm", "t1", True, 6.0),
    ]
    by_backend = {s.keys["backend"]: s for s in summarize(records, ("backend",))}
    assert by_backend["monolithic"].n == 2
    assert by_backend["monolithic"].accuracy == 0.5   # 1 of 2 correct
    assert by_backend["swarm"].accuracy == 1.0
    assert round(by_backend["monolithic"].latency_s.mean, 1) == 3.0


def test_pareto_frontier_minimize_x_maximize_y():
    pts = [
        {"backend": "mono", "latency": 2.0, "accuracy": 0.6},   # cheap, ok
        {"backend": "agentic", "latency": 5.0, "accuracy": 0.9}, # dear, best
        {"backend": "swarm", "latency": 6.0, "accuracy": 0.7},   # dominated by agentic
    ]
    front = {p["backend"] for p in pareto_frontier(pts, "latency", "accuracy")}
    assert front == {"mono", "agentic"}               # swarm is dominated


def test_error_distribution_counts_only_failures():
    records = [
        _rec("agentic", "t1", False, 3.0, err="reasoning_error"),
        _rec("agentic", "t2", False, 3.0, err="reasoning_error"),
        _rec("agentic", "t3", False, 3.0, err="format_error"),
        _rec("agentic", "t4", True, 3.0),            # correct -> not counted
    ]
    dist = error_distribution(records, "backend")
    assert dist["agentic"]["reasoning_error"] == 2
    assert dist["agentic"]["format_error"] == 1
    assert sum(dist["agentic"].values()) == 3


def test_load_records_roundtrip(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text("\n".join(json.dumps(_rec("monolithic", "t1", True, 1.0)) for _ in range(3)))
    assert len(load_records([p, tmp_path / "missing.jsonl"])) == 3


def test_build_report_contains_expected_sections():
    records = [
        _rec("monolithic", "t1", True, 2.0),
        _rec("agentic", "t1", True, 5.0, actions=2),
        _rec("swarm", "t1", False, 6.0, err="reasoning_error"),
    ]
    md = build_report(records)
    assert "# Benchmark Analysis" in md
    assert "By architecture" in md
    assert "Pareto frontiers" in md
    assert "Error distribution" in md
    assert "monolithic" in md and "agentic" in md and "swarm" in md


def test_build_report_handles_empty():
    assert "No result rows" in build_report([])
