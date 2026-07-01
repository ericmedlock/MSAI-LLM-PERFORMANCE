"""Analyze CLI writes a Markdown report from result files."""

from __future__ import annotations

import json

from harness.analyze import main


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _rec(backend, correct, latency):
    return {
        "backend": backend, "task_id": "t1", "environment": "local",
        "model_tag": "deepseek", "correct": correct, "error_category": None,
        "latency_s": latency, "tokens_in": 10, "tokens_out": 20,
        "total_tokens": 30, "tokens_per_s": 5.0, "action_count": 1,
        "telemetry": {"peak_ram_mb": 100.0},
    }


def test_analyze_writes_report(tmp_path, capsys):
    res = tmp_path / "local.jsonl"
    _write(res, [_rec("monolithic", True, 2.0), _rec("swarm", False, 6.0)])
    out = tmp_path / "analysis.md"
    rc = main(["--results", str(res), "--output", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "# Benchmark Analysis" in text
    assert "monolithic" in text and "swarm" in text
    assert "Wrote report" in capsys.readouterr().out
