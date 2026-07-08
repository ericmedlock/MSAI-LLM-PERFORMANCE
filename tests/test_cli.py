"""CLI wiring: dry-run plans correctly and validates task ids, without ever
contacting a model."""

from __future__ import annotations

import pytest

import harness.run as run_module
from harness.run import main


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Isolate the banner assertions from a developer's local ``.env``.

    ``main()`` calls ``load_dotenv()`` which reads ``./.env`` at runtime, so a
    dev override (e.g. MODEL_TAG/LLM_MODEL on a prototyping box) would otherwise
    change the plan banner these tests assert on. Neutralize both the file read
    and any already-exported overrides so the tests see the committed defaults.
    """
    monkeypatch.setattr(run_module, "load_dotenv", lambda *a, **k: {})
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "MODEL_TAG", "MODEL_QUANT"):
        monkeypatch.delenv(var, raising=False)


def test_dry_run_reports_plan_and_does_not_call_model(capsys):
    rc = main(["--backend", "monolithic", "--task-id", "gsm8k-001", "--trials", "5", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "Provider    : openai @ http://localhost:1234/v1" in out  # LM Studio
    assert "deepseek-r1-distill-qwen-14b" in out
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
    assert "Total cells : 225 runs" in out  # 15 tasks x 3 backends x 5 trials
