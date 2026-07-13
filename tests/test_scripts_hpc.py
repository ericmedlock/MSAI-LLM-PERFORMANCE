"""Regression tests for the HPC deployment shell scripts.

These exercise the real scripts as subprocesses with a controlled environment.
Everything here is offline: no model server is contacted (DRYRUN / --offline /
guard refusals all exit before any network or GPU touch), so the suite is safe
to run while a benchmark is in progress on this machine.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PINNED_TAG = "deepseek-r1-14b-distill-q4_k_m"


def run_script(args, *, env_extra=None, cwd=REPO):
    env = os.environ.copy()
    env.pop("MODEL_TAG", None)  # tests control overrides explicitly
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120
    )


def test_scripts_parse(tmp_path):
    for script in ["scripts/setup.sh", "scripts/run_trials.sh",
                   "scripts/bootstrap_model_server.sh", "scripts/job_frontier_a40.sbatch"]:
        proc = run_script(["-n", str(REPO / script)])
        assert proc.returncode == 0, f"{script} has a syntax error:\n{proc.stderr}"


def test_dryrun_prints_plan_and_exits_before_launch(tmp_path):
    out = tmp_path / "plan-only.jsonl"
    proc = run_script(
        ["scripts/run_trials.sh", "local"],
        env_extra={"DRYRUN": "1", "OUT": str(out), "TRIALS": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "DRYRUN=1" in proc.stdout
    assert not out.exists()  # plan only: nothing was launched, nothing written


def test_dryrun_defaults_to_v21_manifest():
    proc = run_script(
        ["scripts/run_trials.sh", "local"],
        env_extra={"DRYRUN": "1", "OUT": "/dev/null", "TRIALS": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "manifest=tasks/frontier_v2_1_manifest.json" in proc.stdout


def test_output_guard_refuses_foreign_model_tag(tmp_path):
    out = tmp_path / "poisoned.jsonl"
    out.write_text(json.dumps({"model_tag": "some-other-model", "trial_idx": 1}) + "\n")
    proc = run_script(
        ["scripts/run_trials.sh", "local"],
        env_extra={"DRYRUN": "1", "OUT": str(out), "TRIALS": "1"},
    )
    assert proc.returncode != 0
    assert "REFUSING" in proc.stderr
    assert out.read_text().count("\n") == 1  # untouched


def test_output_guard_allows_resume_of_matching_tag(tmp_path):
    out = tmp_path / "resume.jsonl"
    out.write_text(json.dumps({"model_tag": PINNED_TAG, "trial_idx": 1}) + "\n")
    proc = run_script(
        ["scripts/run_trials.sh", "local"],
        env_extra={"DRYRUN": "1", "OUT": str(out), "TRIALS": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "guard OK" in proc.stdout


def test_output_guard_honors_model_tag_override(tmp_path):
    # A scaling leg (MODEL_TAG=...-32b) resuming its own file must pass.
    out = tmp_path / "leg32b.jsonl"
    out.write_text(json.dumps({"model_tag": "deepseek-r1-distill-qwen-32b"}) + "\n")
    proc = run_script(
        ["scripts/run_trials.sh", "local"],
        env_extra={"DRYRUN": "1", "OUT": str(out), "TRIALS": "1",
                   "MODEL_TAG": "deepseek-r1-distill-qwen-32b"},
    )
    assert proc.returncode == 0, proc.stderr


def test_setup_offline_passes_when_artifacts_present(tmp_path):
    # Fake a complete artifact set so the check is hermetic on any machine.
    cache = tmp_path / "models"
    (cache / "manifests/registry.ollama.ai/library/deepseek-r1").mkdir(parents=True)
    (cache / "manifests/registry.ollama.ai/library/deepseek-r1/14b").write_text("{}")
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    (fakebin / "ollama").write_text("#!/bin/sh\nexit 0\n")
    (fakebin / "ollama").chmod(0o755)
    proc = run_script(
        ["scripts/setup.sh", "--offline"],
        env_extra={"OLLAMA_MODELS": str(cache), "PATH": f"{fakebin}:{os.environ['PATH']}"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ready to run" in proc.stdout


def test_setup_offline_fails_fast_with_remedy_when_model_missing(tmp_path):
    empty = tmp_path / "empty-cache"
    empty.mkdir()
    proc = run_script(
        ["scripts/setup.sh", "--offline"],
        env_extra={"OLLAMA_MODELS": str(empty)},
    )
    assert proc.returncode != 0
    assert "MISSING" in proc.stdout
    assert "--download" in proc.stdout  # the named remedy


def test_setup_offline_makes_no_network_or_install_attempt(tmp_path):
    # Even with everything missing it must only report — never curl/pip.
    empty = tmp_path / "nothing"
    empty.mkdir()
    proc = run_script(
        ["scripts/setup.sh", "--offline"],
        env_extra={"OLLAMA_MODELS": str(empty)},
    )
    assert "downloading" not in proc.stdout.lower()
    assert "pip install" not in proc.stdout.lower()


@pytest.mark.parametrize("job_id,expected_port", [("1234", str(20000 + 1234 % 20000))])
def test_slurm_job_gets_private_port(tmp_path, job_id, expected_port):
    # hpc profile inside a fake SLURM job: DRYRUN exits before any server
    # contact, but the port derivation must already be visible in the log.
    proc = run_script(
        ["scripts/run_trials.sh", "hpc"],
        env_extra={"DRYRUN": "1", "OUT": str(tmp_path / "o.jsonl"), "TRIALS": "1",
                   "SLURM_JOB_ID": job_id},
    )
    assert proc.returncode == 0, proc.stderr
    assert f"private server port {expected_port}" in proc.stdout
