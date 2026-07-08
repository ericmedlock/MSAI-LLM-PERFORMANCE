"""Results store is append-only, crash-safe, and resumable."""

from __future__ import annotations

from harness.results import RunRecord, append_record, completed_keys


def _record(task_id="gsm8k-001", backend="monolithic", env="local", trial=1):
    return RunRecord(
        run_id="r", timestamp="t", backend=backend, environment=env,
        task_id=task_id, task_domain="gsm8k", task_tier="baseline", trial_idx=trial,
        model_tag="m", config_hash="h", answer="72", correct=True,
        error_category=None, latency_s=1.0, tokens_in=1, tokens_out=1,
        total_tokens=2, tokens_per_s=1.0, action_count=1,
    )


def test_append_and_completed_keys_roundtrip(tmp_path):
    path = tmp_path / "local.jsonl"
    assert completed_keys(path) == set()
    append_record(path, _record(trial=1))
    append_record(path, _record(trial=2))
    keys = completed_keys(path)
    assert ("gsm8k-001", "monolithic", "local", 1) in keys
    assert ("gsm8k-001", "monolithic", "local", 2) in keys
    assert len(keys) == 2


def test_partial_trailing_line_is_tolerated(tmp_path):
    path = tmp_path / "local.jsonl"
    append_record(path, _record(trial=1))
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"task_id": "gsm8k-001", "backend": "mono')  # crash mid-write
    keys = completed_keys(path)  # must not raise
    assert keys == {("gsm8k-001", "monolithic", "local", 1)}


def test_run_key_identity():
    assert _record(trial=3).key() == ("gsm8k-001", "monolithic", "local", 3)
