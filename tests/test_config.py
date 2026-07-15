"""Config loads the pinned values and enforces the scientific invariants."""

from __future__ import annotations

import pytest

from harness.config import load_config
from tests.conftest import ROOT


def test_pinned_values_match_preregistration(config):
    assert config.model.tag == "deepseek-r1-14b-distill-q4_k_m"  # canonical identity
    assert config.model.quantization == "Q4_K_M"
    # temp 0.0 -> 0.6 and per-trial seed offsets (amended 2026-07-15): at temp 0
    # with a seed fixed across trials, every trial was the same deterministic
    # computation, so N measured nothing (engineering log §9).
    assert config.decoding.temperature == 0.6
    assert config.decoding.num_ctx == 8192
    assert config.decoding.max_tokens == 6144  # raised from 2048; see Amendment Log
    assert config.trials_n == 5
    assert config.trial_seed_strategy == "offset"       # amended 2026-07-15
    assert config.trial_seed_stride > config.swarm.num_agents  # no peer/trial seed collision
    assert config.agentic.max_loops == 2
    assert config.swarm.num_agents == 3
    assert config.swarm.aggregation == "majority_vote"
    assert config.swarm.tie_break == "lowest_agent_index"
    assert config.swarm.peer_seed_strategy == "offset"  # amended 2026-07-01


def test_both_environments_defined(config):
    # The two PRE-REGISTERED cells must always exist; additional compute
    # environments (shadow trial, HPC) are allowed on top (2026-07-10).
    assert {"local", "cloud"} <= set(config.environments)
    local, cloud = config.env("local"), config.env("cloud")
    assert local.runtime == "metal" and local.provider == "openai"   # LM Studio
    assert local.base_url == "http://localhost:1234/v1"
    assert cloud.runtime == "cuda" and cloud.provider == "ollama"
    # every extra environment must still be fully specified for the harness
    for key in set(config.environments) - {"local", "cloud"}:
        extra = config.env(key)
        assert extra.provider in {"openai", "ollama"} and extra.base_url
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


def test_model_label_overrides_for_dev_but_defaults_to_pinned(config):
    # a dev box serving a different model overrides the canonical label
    m = config.model.resolved({"MODEL_TAG": "gemma-4-e4b", "MODEL_QUANT": "Q4"})
    assert m.tag == "gemma-4-e4b" and m.quantization == "Q4"
    # unset -> pinned identity from config.yaml is preserved (pre-registered runs)
    assert config.model.resolved({}).tag == config.model.tag


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


def test_trial_seed_offset_gives_each_trial_an_independent_draw(config):
    # Amendment 2026-07-15 / engineering log §9: at temp 0 with one shared seed,
    # all N trials were the SAME deterministic computation (~98% of N=5 cells
    # returned identical verdicts). Each trial must now draw its own seed.
    seeds = [config.trial_seed(t) for t in range(1, 6)]
    assert len(set(seeds)) == 5                       # every trial differs
    assert seeds == [42 + t * 1000 for t in range(1, 6)]


def test_trial_seed_stride_prevents_peer_trial_collision(config):
    # swarm peer i draws trial_seed + i. If the trial stride were <= num_agents,
    # trial t's peers would overlap trial t+1's -> correlated trials, i.e. the
    # very flaw being removed. Assert the seed SPACES are disjoint.
    n = config.swarm.num_agents
    spaces = [
        {config.trial_seed(t) + i for i in range(n)}
        for t in range(1, 6)
    ]
    union = set().union(*spaces)
    assert len(union) == n * 5                        # no seed reused across trials


def test_trial_seed_same_strategy_restores_pinned_behavior(config):
    import dataclasses

    pinned = dataclasses.replace(config, trial_seed_strategy="same")
    assert [pinned.trial_seed(t) for t in range(1, 4)] == [None, None, None]
