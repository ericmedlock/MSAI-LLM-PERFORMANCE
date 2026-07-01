"""Config loads the pinned values and enforces the scientific invariants."""

from __future__ import annotations

import pytest

from harness.config import load_config
from tests.conftest import ROOT


def test_pinned_values_match_preregistration(config):
    assert config.model.tag == "deepseek-r1-14b-distill-q4_k_m"  # canonical identity
    assert config.model.quantization == "Q4_K_M"
    assert config.decoding.temperature == 0.0          # determinism
    assert config.decoding.num_ctx == 8192
    assert config.decoding.max_tokens == 6144  # raised from 2048; see Amendment Log
    assert config.trials_n == 5
    assert config.agentic.max_loops == 2
    assert config.swarm.num_agents == 3
    assert config.swarm.aggregation == "majority_vote"
    assert config.swarm.tie_break == "lowest_agent_index"
    assert config.swarm.peer_seed_strategy == "offset"  # amended 2026-07-01


def test_both_environments_defined(config):
    assert set(config.environments) == {"local", "cloud"}
    local, cloud = config.env("local"), config.env("cloud")
    assert local.runtime == "metal" and local.provider == "openai"   # LM Studio
    assert local.base_url == "http://localhost:1234/v1"
    assert cloud.runtime == "cuda" and cloud.provider == "ollama"
    # default resolves to the active environment
    assert config.env().key == config.active_environment


def test_env_overrides_from_environment_variables(config):
    env = config.env("local").resolved(
        {"LLM_PROVIDER": "ollama", "LLM_BASE_URL": "http://box:11434", "LLM_MODEL": "x:14b"}
    )
    assert env.provider == "ollama"
    assert env.base_url == "http://box:11434"
    assert env.model == "x:14b"
    # unset override leaves the committed value intact
    assert config.env("local").resolved({}).base_url == "http://localhost:1234/v1"


def test_api_key_falls_back_when_unset(config):
    assert config.env("local").api_key({}) == "lm-studio"
    assert config.env("local").api_key({"LLM_API_KEY": "secret"}) == "secret"


def test_load_dotenv_parses_and_respects_existing(tmp_path, monkeypatch):
    from harness.config import load_dotenv

    envfile = tmp_path / ".env"
    envfile.write_text('# comment\nLLM_MODEL="foo-14b"\nLLM_BASE_URL=http://h:1234/v1\n')
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://preexisting")  # must NOT be overwritten
    parsed = load_dotenv(envfile)
    assert parsed["LLM_MODEL"] == "foo-14b"
    import os

    assert os.environ["LLM_MODEL"] == "foo-14b"          # newly set
    assert os.environ["LLM_BASE_URL"] == "http://preexisting"  # preserved


def test_config_hash_is_stable_and_16_hex(config):
    again = load_config(ROOT / "config" / "config.yaml")
    assert config.config_hash == again.config_hash
    assert len(config.config_hash) == 16
    int(config.config_hash, 16)  # parses as hex


def test_unknown_environment_raises(config):
    with pytest.raises(KeyError):
        config.env("does-not-exist")


def test_missing_required_key_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("active_environment: local\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_config(bad)
