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


def _make_client(
    provider: str, base_url: str, model: str, decoding, api_key: str
) -> LLMClient:
    """Construct a provider client. Concrete HTTP clients are imported lazily
    so offline tests never require them."""
    if provider == "ollama":
        from backends.llm_client import OllamaClient

        return OllamaClient(
            endpoint=base_url,
            model_tag=model,
            temperature=decoding.temperature,
            num_ctx=decoding.num_ctx,
            max_tokens=decoding.max_tokens,
            seed=decoding.seed,
        )
    if provider in ("openai", "openai-compatible", "lmstudio"):
        from backends.llm_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            base_url=base_url,
            model_tag=model,
            temperature=decoding.temperature,
            num_ctx=decoding.num_ctx,
            max_tokens=decoding.max_tokens,
            seed=decoding.seed,
            api_key=api_key,
        )
    raise ValueError(f"unknown provider {provider!r}")


def build_client(config: Config, environment: str | None = None) -> LLMClient:
    """Build the backend LLM client for an environment, selected by provider.

    Endpoint/provider/model/key are resolved with per-machine ``.env``
    overrides; pinned decoding parameters come from config.
    """
    env = config.env(environment).resolved()
    try:
        return _make_client(env.provider, env.base_url, env.model, config.decoding, env.api_key())
    except ValueError as exc:
        raise ValueError(f"{exc} for environment {env.key!r}") from None


def build_judge_client(config: Config) -> LLMClient:
    """Build the LLM-as-judge client (different-family model, temp 0.0)."""
    judge = config.judge.resolved()
    try:
        return _make_client(
            judge.provider, judge.base_url, judge.model, config.decoding, judge.api_key()
        )
    except ValueError as exc:
        raise ValueError(f"{exc} for judge") from None
