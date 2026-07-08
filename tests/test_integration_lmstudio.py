"""Live end-to-end test against a running model server (LM Studio by default).

Skipped automatically when no server is reachable, so the offline suite stays
green. Run explicitly against LM Studio with:

    ./.venv/bin/python -m pytest tests/test_integration_lmstudio.py -m integration -rs

Point it elsewhere via .env / env vars (LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER).
"""

from __future__ import annotations

import os

import pytest

from backends.factory import build_backend, build_client
from harness.config import load_config
from harness.graders import grade
from harness.prompts import load_prompts
from tests.conftest import ROOT

pytestmark = pytest.mark.integration


def _reachable(base_url: str) -> bool:
    import requests

    try:
        # /models works for both openai (/v1/models) and is harmless elsewhere
        return requests.get(f"{base_url.rstrip('/')}/models", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def live_env():
    config = load_config(ROOT / "config" / "config.yaml")
    env = config.env(os.environ.get("LLM_ENV", "local")).resolved()
    if not _reachable(env.base_url):
        pytest.skip(f"no model server reachable at {env.base_url}")
    return config, env


def test_monolithic_solves_gsm8k_end_to_end(live_env):
    config, _ = live_env
    prompts = load_prompts(config.prompts_dir)
    client = build_client(config)
    backend = build_backend("monolithic", client=client, config=config, prompts=prompts)

    from backends.base import Task

    task = Task(
        "gsm8k-001", "gsm8k",
        "Natalia sold clips to 48 of her friends in April, and then she sold half "
        "as many clips in May. How many clips did she sell altogether?",
        answer="72",
    )
    result = backend.run(task)
    correct, _ = grade(task, result.answer)

    assert result.tokens_in > 0 and result.tokens_out > 0
    assert result.latency_s > 0
    assert correct, f"expected 72, model answered: {result.answer[-120:]!r}"


def test_swarm_runs_three_real_peers(live_env):
    config, _ = live_env
    prompts = load_prompts(config.prompts_dir)
    client = build_client(config)
    backend = build_backend("swarm", client=client, config=config, prompts=prompts)

    from backends.base import Task

    task = Task("gsm8k-002", "gsm8k", "Weng earns $12 an hour. She babysat 50 minutes. How much did she earn?", answer="10")
    result = backend.run(task)

    assert result.action_count == 3
    assert result.metadata["num_agents"] == 3
    assert "vote_counts" in result.metadata
