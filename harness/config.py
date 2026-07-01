"""Typed loader for ``config/config.yaml``.

Per the pre-registration, every value that must be held constant across
experimental cells -- model tag/digest, quantization, temperature, context
window, max tokens, seed, N, and the architecture parameters -- lives in
config and is loaded here. Nothing pinned is hardcoded in Python.

A ``config_hash`` is derived from the raw file bytes and stamped onto every
telemetry row so any result can be tied back to the exact config that
produced it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelConfig:
    tag: str
    quantization: str
    digest: str  # pinned from `ollama show <tag>` at freeze; provenance check


@dataclass(frozen=True)
class DecodingConfig:
    temperature: float
    num_ctx: int
    max_tokens: int
    seed: int


@dataclass(frozen=True)
class AgenticConfig:
    max_loops: int


@dataclass(frozen=True)
class SwarmConfig:
    num_agents: int
    aggregation: str
    tie_break: str
    peer_seed_strategy: str  # "offset" | "same"


@dataclass(frozen=True)
class EnvironmentConfig:
    key: str
    name: str
    ollama_endpoint: str
    runtime: str  # "metal" | "cuda" | "cpu"


@dataclass(frozen=True)
class Config:
    active_environment: str
    model: ModelConfig
    decoding: DecodingConfig
    agentic: AgenticConfig
    swarm: SwarmConfig
    environments: dict[str, EnvironmentConfig]
    trials_n: int
    tasks_manifest: str
    prompts_dir: str
    results_dir: str
    config_hash: str

    def env(self, key: str | None = None) -> EnvironmentConfig:
        """Resolve the active environment (or an explicit override)."""
        key = key or self.active_environment
        if key not in self.environments:
            raise KeyError(
                f"environment {key!r} not defined; known: {sorted(self.environments)}"
            )
        return self.environments[key]


def _require(mapping: dict[str, Any], *keys: str) -> Any:
    node: Any = mapping
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            raise KeyError(f"config missing required key: {'.'.join(keys)}")
        node = node[k]
    return node


def load_config(path: str | Path) -> Config:
    raw_bytes = Path(path).read_bytes()
    data = yaml.safe_load(raw_bytes)
    config_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

    environments: dict[str, EnvironmentConfig] = {}
    for key, env in _require(data, "environments").items():
        environments[key] = EnvironmentConfig(
            key=key,
            name=env["name"],
            ollama_endpoint=env["ollama_endpoint"],
            runtime=env["runtime"],
        )

    active = _require(data, "active_environment")
    if active not in environments:
        raise ValueError(
            f"active_environment {active!r} is not defined under environments"
        )

    return Config(
        active_environment=active,
        model=ModelConfig(
            tag=_require(data, "model", "tag"),
            quantization=_require(data, "model", "quantization"),
            digest=data["model"].get("digest", ""),
        ),
        decoding=DecodingConfig(
            temperature=float(_require(data, "decoding", "temperature")),
            num_ctx=int(_require(data, "decoding", "num_ctx")),
            max_tokens=int(_require(data, "decoding", "max_tokens")),
            seed=int(_require(data, "decoding", "seed")),
        ),
        agentic=AgenticConfig(max_loops=int(_require(data, "architectures", "agentic", "max_loops"))),
        swarm=SwarmConfig(
            num_agents=int(_require(data, "architectures", "swarm", "num_agents")),
            aggregation=_require(data, "architectures", "swarm", "aggregation"),
            tie_break=_require(data, "architectures", "swarm", "tie_break"),
            peer_seed_strategy=_require(data, "architectures", "swarm", "peer_seed_strategy"),
        ),
        environments=environments,
        trials_n=int(_require(data, "trials", "n")),
        tasks_manifest=_require(data, "tasks_manifest"),
        prompts_dir=_require(data, "prompts_dir"),
        results_dir=_require(data, "results_dir"),
        config_hash=config_hash,
    )
