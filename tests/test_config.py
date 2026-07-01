"""Config loads the pinned values and enforces the scientific invariants."""

from __future__ import annotations

import pytest

from harness.config import load_config
from tests.conftest import ROOT


def test_pinned_values_match_preregistration(config):
    assert config.model.tag == "deepseek-r1:14b"
    assert config.model.quantization == "Q4_K_M"
    assert config.decoding.temperature == 0.0          # determinism
    assert config.decoding.num_ctx == 8192
    assert config.decoding.max_tokens == 2048
    assert config.trials_n == 5
    assert config.agentic.max_loops == 2
    assert config.swarm.num_agents == 3
    assert config.swarm.aggregation == "majority_vote"
    assert config.swarm.tie_break == "lowest_agent_index"
    assert config.swarm.peer_seed_strategy == "offset"  # amended 2026-07-01


def test_both_environments_defined(config):
    assert set(config.environments) == {"local", "cloud"}
    assert config.env("local").runtime == "metal"
    assert config.env("cloud").runtime == "cuda"
    # default resolves to the active environment
    assert config.env().key == config.active_environment


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
