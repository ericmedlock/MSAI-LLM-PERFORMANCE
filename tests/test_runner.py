"""End-to-end runner (offline): plan -> graded rows, idempotent + resumable."""

from __future__ import annotations

import itertools
import json

from backends.base import Task
from harness.runner import RunPlan, Runner
from harness.telemetry import NoopCollector
from tests.conftest import FakeLLMClient

TASKS = [
    Task("gsm8k-001", "gsm8k", "Natalia...", answer="72"),
    Task("hotpotqa-001", "hotpotqa", "Which magazine...", answer="Arthur's Magazine"),
]


def _runner(config, prompts, responder):
    counter = itertools.count(1)
    return Runner(
        config=config,
        client=FakeLLMClient(responder),
        prompts=prompts,
        collector_factory=lambda rt: NoopCollector(),
        clock=lambda: 1_700_000_000.0,             # fixed, deterministic timestamp
        run_id_factory=lambda: f"run-{next(counter)}",
    )


def test_host_profile_written_beside_output_not_frozen_results(config, prompts, tmp_path, monkeypatch):
    # Provenance sidecar must follow the output path (co-located), never rewrite
    # the frozen results/host/*.json + hosts.csv. Regression for the isolation bug.
    import harness.hostinfo as hostinfo

    monkeypatch.setattr(hostinfo, "_loaded_models", lambda provider, base_url: ["m1"])
    out = tmp_path / "local.jsonl"
    runner = _runner(config, prompts, lambda s, u, seed: "72")
    runner.run_plan(RunPlan("local", ["monolithic"], TASKS[:1], trials=1), out)

    assert (tmp_path / "host" / "local.json").exists()   # sidecar beside the output
    assert (tmp_path / "hosts.csv").exists()


def test_run_plan_writes_n_rows_per_cell_and_grades(config, prompts, tmp_path):
    out = tmp_path / "local.jsonl"
    # correct answer for both tasks
    responder = lambda s, u, seed: "72" if "Natalia" in u else "Arthur's Magazine"
    runner = _runner(config, prompts, responder)
    plan = RunPlan(environment="local", backends=["monolithic"], tasks=TASKS, trials=3)

    written = runner.run_plan(plan, out)
    assert written == 2 * 1 * 3  # tasks x backends x trials

    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(rows) == 6
    assert all(r["environment"] == "local" for r in rows)
    assert all(r["correct"] is True for r in rows)
    assert all(r["config_hash"] == config.config_hash for r in rows)
    # trial indices are 1..N per task
    gsm = sorted(r["trial_idx"] for r in rows if r["task_id"] == "gsm8k-001")
    assert gsm == [1, 2, 3]


def test_run_plan_is_idempotent_on_rerun(config, prompts, tmp_path):
    out = tmp_path / "local.jsonl"
    responder = lambda s, u, seed: "72" if "Natalia" in u else "Arthur's Magazine"
    runner = _runner(config, prompts, responder)
    plan = RunPlan(environment="local", backends=["monolithic"], tasks=TASKS, trials=2)

    first = runner.run_plan(plan, out)
    second = runner.run_plan(plan, out)  # nothing new to do
    assert first == 4
    assert second == 0
    assert len(out.read_text().splitlines()) == 4


def test_resume_tops_up_only_missing_rows(config, prompts, tmp_path):
    out = tmp_path / "local.jsonl"
    responder = lambda s, u, seed: "72" if "Natalia" in u else "Arthur's Magazine"
    runner = _runner(config, prompts, responder)

    runner.run_plan(
        RunPlan("local", ["monolithic"], TASKS, trials=1), out
    )  # 2 rows
    # now ask for 3 trials: only the 4 missing (trials 2,3 x 2 tasks) are added
    added = runner.run_plan(RunPlan("local", ["monolithic"], TASKS, trials=3), out)
    assert added == 4
    assert len(out.read_text().splitlines()) == 6


def test_backend_exception_is_recorded_not_fatal(config, prompts, tmp_path):
    out = tmp_path / "local.jsonl"

    def boom(system, user, seed):
        raise RuntimeError("model down")

    runner = _runner(config, prompts, boom)
    written = runner.run_plan(
        RunPlan("local", ["monolithic"], [TASKS[0]], trials=1), out
    )
    assert written == 1
    row = json.loads(out.read_text().splitlines()[0])
    assert row["correct"] is False
    assert row["error_category"] == "backend_exception"
    assert "model down" in row["metadata"]["exception"]
