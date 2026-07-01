"""Shared contract every backend must fulfil.

The benchmark harness talks *only* to :class:`Backend` and consumes
:class:`BackendResult`. It has no knowledge of which architecture runs
underneath. This is the core design decision that makes the study
scientifically valid: the only thing that changes between experimental
cells is the concrete ``Backend`` implementation and the environment it
runs in -- never the harness, the model, the prompts, or the task inputs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Task:
    """A single frozen benchmark item.

    Loaded from ``tasks/manifest.json`` and never mutated during a run.
    """

    task_id: str
    domain: str                      # "gsm8k" | "humaneval" | "hotpotqa" | "math" | "code"
    prompt: str                      # the user-facing question / instruction
    answer: Optional[str] = None     # expected answer (gsm8k number, hotpotqa string)
    grading: dict = field(default_factory=dict)  # grader payload (humaneval: test + entry_point)
    source_id: Optional[str] = None  # original benchmark item id (for provenance)
    tier: str = "baseline"           # "baseline" (v1) | "frontier" (architecture-favoring)


@dataclass
class BackendResult:
    """Uniform output schema returned by all three backends.

    ``correct`` is intentionally left ``None`` here -- the backend never
    grades itself. The harness fills it in by calling the domain grader,
    keeping generation and evaluation strictly separated.
    """

    answer: str
    latency_s: float
    tokens_in: int
    tokens_out: int
    action_count: int                       # number of LLM calls / agent turns
    raw_trace: str                          # full interaction transcript (JSON string)
    error_category: Optional[str] = None    # populated on failure (Gupta taxonomy)
    correct: Optional[bool] = None          # filled by the grader, not the backend
    metadata: dict = field(default_factory=dict)  # backend-specific extras


class Backend(ABC):
    """Abstract base class all three architectures implement.

    Concrete backends receive their dependencies by injection (an
    ``LLMClient`` and a frozen config/prompt set) so they can be unit
    tested offline against a stubbed model.
    """

    #: short stable identifier written to every telemetry row
    name: str = "base"

    @abstractmethod
    def run(self, task: Task) -> BackendResult:
        """Execute ``task`` and return a uniform :class:`BackendResult`."""
        raise NotImplementedError

    def health_check(self) -> bool:  # pragma: no cover - trivial default
        """Return ``True`` if the backend is reachable and ready."""
        return True
