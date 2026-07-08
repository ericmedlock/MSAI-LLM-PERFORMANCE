"""Load frozen, version-controlled system prompts from ``prompts/``.

Kept deliberately dumb: prompts are files, this reads them. Backends never
embed prompt text inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptSet:
    monolithic_system: str
    executor_system: str
    verifier_system: str
    peer_system: str


def load_prompts(prompts_dir: str | Path) -> PromptSet:
    root = Path(prompts_dir)

    def read(*parts: str) -> str:
        return (root.joinpath(*parts)).read_text(encoding="utf-8").strip()

    return PromptSet(
        monolithic_system=read("monolithic", "system.txt"),
        executor_system=read("agentic", "executor_system.txt"),
        verifier_system=read("agentic", "verifier_system.txt"),
        peer_system=read("swarm", "peer_system.txt"),
    )
