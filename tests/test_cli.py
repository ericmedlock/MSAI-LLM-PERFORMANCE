"""CLI wiring: dry-run plans correctly and validates task ids, without ever
contacting a model."""

from __future__ import annotations

from harness.run import main


def test_dry_run_reports_plan_and_does_not_call_model(capsys):
    rc = main(["--backend", "monolithic", "--task-id", "gsm8k-001", "--trials", "5", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "deepseek-r1:14b" in out
    assert "Total cells : 5 runs" in out


def test_unknown_task_id_errors(capsys):
    rc = main(["--task-id", "nope-999", "--dry-run"])
    assert rc == 2
    assert "unknown task id" in capsys.readouterr().err


def test_default_plan_is_all_backends_all_tasks_n5(capsys):
    rc = main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "monolithic, agentic, swarm" in out
    assert "Total cells : 135 runs" in out  # 9 tasks x 3 backends x 5 trials
