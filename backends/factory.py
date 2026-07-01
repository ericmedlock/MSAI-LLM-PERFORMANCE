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


def build_client(config: Config, environment: str | None = None) -> LLMClient:
    """Build the LLM client for an environment, selected by provider.

    Endpoint/provider/model/key are resolved with per-machine ``.env``
    overrides applied; the pinned decoding parameters come from config.
    Concrete HTTP clients are imported lazily so offline tests never need them.
    """
    env = config.env(environment).resolved()
    decoding = config.decoding
    if env.provider == "ollama":
        from backends.llm_client import OllamaClient

        return OllamaClient(
            endpoint=env.base_url,
            model_tag=env.model,
            temperature=decoding.temperature,
            num_ctx=decoding.num_ctx,
            max_tokens=decoding.max_tokens,
            seed=decoding.seed,
        )
    if env.provider in ("openai", "openai-compatible", "lmstudio"):
        from backends.llm_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            base_url=env.base_url,
            model_tag=env.model,
            temperature=decoding.temperature,
            num_ctx=decoding.num_ctx,
            max_tokens=decoding.max_tokens,
            seed=decoding.seed,
            api_key=env.api_key(),
        )
    raise ValueError(f"unknown provider {env.provider!r} for environment {env.key!r}")
