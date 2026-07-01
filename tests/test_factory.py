"""Factory builds each backend from pinned config, and the Ollama client
carries the pinned decoding parameters (constructed, never contacted)."""

from __future__ import annotations

import pytest

from backends.agentic import AgenticBackend
from backends.factory import build_backend, build_ollama_client
from backends.llm_client import OllamaClient
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


def test_unknown_backend_rejected(config, prompts):
    with pytest.raises(ValueError, match="unknown backend"):
        build_backend("mixture", client=FakeLLMClient(), config=config, prompts=prompts)


def test_ollama_client_carries_pinned_params(config):
    client = build_ollama_client(config, "cloud")
    assert isinstance(client, OllamaClient)
    assert client.model_tag == config.model.tag
    assert client.temperature == 0.0
    assert client.num_ctx == config.decoding.num_ctx
    assert client.seed == config.decoding.seed
    assert client.endpoint == config.env("cloud").ollama_endpoint.rstrip("/")


def test_swarm_same_seed_strategy_disables_offset(prompts):
    from backends.base import Task

    seeds = []
    client = FakeLLMClient(lambda s, u, seed: (seeds.append(seed) or "answer 72"))
    SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index",
        base_seed=42, peer_seed_strategy="same",
    ).run(Task("t", "gsm8k", "q", answer="72"))
    assert seeds == [42, 42, 42]
