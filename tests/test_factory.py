"""Factory builds each backend from pinned config, and the Ollama client
carries the pinned decoding parameters (constructed, never contacted)."""

from __future__ import annotations

import pytest

from backends.agentic import AgenticBackend
from backends.factory import build_backend, build_client
from backends.llm_client import OllamaClient, OpenAICompatibleClient
from backends.monolithic import MonolithicBackend
from backends.swarm import SwarmBackend
from tests.conftest import FakeLLMClient


def test_build_each_backend_type(config, prompts):
    client = FakeLLMClient()
    assert isinstance(build_backend("monolithic", client=client, config=config, prompts=prompts), MonolithicBackend)
    a = build_backend("agentic", client=client, config=config, prompts=prompts)
    assert isinstance(a, AgenticBackend) and a._max_loops == config.agentic.max_loops
    s = build_backend("swarm", client=client, config=config, prompts=prompts)
    assert isinstance(s, SwarmBackend) and s._num_agents == config.swarm.num_agents
    # peer-seed strategy is pinned in config, not a code default (amended 2026-07-01)
    assert s._peer_seed_strategy == config.swarm.peer_seed_strategy


def test_unknown_backend_rejected(config, prompts):
    with pytest.raises(ValueError, match="unknown backend"):
        build_backend("mixture", client=FakeLLMClient(), config=config, prompts=prompts)


def test_agentic_verdict_defaults_to_strict(config, prompts, monkeypatch):
    monkeypatch.delenv("AGENTIC_VERDICT", raising=False)
    a = build_backend("agentic", client=FakeLLMClient(), config=config, prompts=prompts)
    assert a._verdict_mode == "strict"


def test_agentic_verdict_env_enables_lenient(config, prompts, monkeypatch):
    # AGENTIC 2.0 knob (Amendment 2026-07-14) — exploratory, opt-in via env
    monkeypatch.setenv("AGENTIC_VERDICT", "lenient")
    a = build_backend("agentic", client=FakeLLMClient(), config=config, prompts=prompts)
    assert a._verdict_mode == "lenient"


def test_agentic_verdict_rejects_unknown_mode(config, prompts, monkeypatch):
    monkeypatch.setenv("AGENTIC_VERDICT", "fuzzy")
    with pytest.raises(ValueError, match="AGENTIC_VERDICT"):
        build_backend("agentic", client=FakeLLMClient(), config=config, prompts=prompts)


def test_build_client_selects_openai_for_lmstudio_local(config, monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    client = build_client(config, "local")
    assert isinstance(client, OpenAICompatibleClient)
    assert client.base_url == "http://localhost:1234/v1"
    assert client.model_tag == "deepseek-r1-distill-qwen-14b"
    assert client.temperature == 0.6                      # pinned (amended 2026-07-15), not overridable
    assert client.max_tokens == config.decoding.max_tokens
    assert client.seed == config.decoding.seed


def test_build_client_selects_ollama_for_cloud(config, monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    client = build_client(config, "cloud")
    assert isinstance(client, OllamaClient)
    assert client.endpoint == "http://localhost:11434"
    assert client.model_tag == "deepseek-r1:14b"


def test_build_client_honors_dotenv_override(config, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://otherbox:11434")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:14b")
    client = build_client(config, "local")  # local is openai in config...
    assert isinstance(client, OllamaClient)  # ...but .env flips it to ollama
    assert client.endpoint == "http://otherbox:11434"
    assert client.model_tag == "qwen2.5:14b"


def test_build_client_timeout_override(config, monkeypatch):
    # Read timeout defaults to 600s but is overridable per-machine: slow boxes
    # (14B reasoning model at ~10 tok/s) need >600s for a full max_tokens turn,
    # else long turns silently become backend_exception timeouts.
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT_S"):
        monkeypatch.delenv(var, raising=False)
    assert build_client(config, "local").timeout_s == 600.0
    monkeypatch.setenv("LLM_TIMEOUT_S", "1800")
    assert build_client(config, "local").timeout_s == 1800.0


def test_swarm_same_seed_strategy_disables_offset(prompts):
    from backends.base import Task

    seeds = []
    client = FakeLLMClient(lambda s, u, seed: (seeds.append(seed) or "answer 72"))
    SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index",
        base_seed=42, peer_seed_strategy="same",
    ).run(Task("t", "gsm8k", "q", answer="72"))
    assert seeds == [42, 42, 42]
