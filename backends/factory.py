"""Construct backends from pinned config + injected client + frozen prompts.

Centralizes the wiring so the runner and tests build backends the same way.
"""

from __future__ import annotations

from backends.agentic import AgenticBackend
from backends.base import Backend
from backends.llm_client import LLMClient
from backends.monolithic import MonolithicBackend
from backends.swarm import SwarmBackend
from harness.config import Config
from harness.prompts import PromptSet

BACKEND_NAMES = ("monolithic", "agentic", "swarm")


def build_backend(
    name: str, *, client: LLMClient, config: Config, prompts: PromptSet
) -> Backend:
    if name == "monolithic":
        return MonolithicBackend(client, prompts)
    if name == "agentic":
        return AgenticBackend(client, prompts, max_loops=config.agentic.max_loops)
    if name == "swarm":
        return SwarmBackend(
            client,
            prompts,
            num_agents=config.swarm.num_agents,
            tie_break=config.swarm.tie_break,
            base_seed=config.decoding.seed,
            peer_seed_strategy=config.swarm.peer_seed_strategy,
        )
    raise ValueError(f"unknown backend {name!r}; expected one of {BACKEND_NAMES}")


def build_ollama_client(config: Config, environment: str | None = None) -> LLMClient:
    """Build the pinned Ollama client for an environment. Imported lazily so
    offline tests never require the concrete HTTP client."""
    from backends.llm_client import OllamaClient

    env = config.env(environment)
    return OllamaClient(
        endpoint=env.ollama_endpoint,
        model_tag=config.model.tag,
        temperature=config.decoding.temperature,
        num_ctx=config.decoding.num_ctx,
        max_tokens=config.decoding.max_tokens,
        seed=config.decoding.seed,
    )
