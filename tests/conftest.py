"""Shared test fixtures.

The whole suite runs offline: no Ollama, no GPU, no network. Backends talk
to a ``FakeLLMClient`` whose responses are fully scripted, so structure and
control-flow can be verified deterministically.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

import pytest

from backends.llm_client import LLMResponse
from harness.config import load_config
from harness.prompts import load_prompts

ROOT = Path(__file__).resolve().parents[1]


class FakeLLMClient:
    """Scriptable stand-in for a real model.

    ``responder(system, user, seed)`` returns the assistant text. Every call
    is recorded on ``.calls`` for assertions.
    """

    def __init__(
        self,
        responder: Callable[[str, str, Optional[int]], str] | None = None,
        *,
        tokens_in: int = 11,
        tokens_out: int = 7,
        delay_s: float = 0.0,
    ) -> None:
        self._responder = responder or (lambda system, user, seed: "the answer is 42\n42")
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self._delay_s = delay_s
        self.calls: list[dict] = []

    def chat(
        self, system: str, user: str, *, seed: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        if self._delay_s:
            time.sleep(self._delay_s)
        self.calls.append(
            {"system": system, "user": user, "seed": seed, "temperature": temperature}
        )
        text = self._responder(system, user, seed)
        return LLMResponse(text=text, tokens_in=self._tokens_in, tokens_out=self._tokens_out)


@pytest.fixture
def config():
    return load_config(ROOT / "config" / "config.yaml")


@pytest.fixture
def prompts():
    return load_prompts(ROOT / "prompts")


@pytest.fixture
def fake_client_factory():
    """Return a factory so tests can build fakes with custom responders."""
    return FakeLLMClient
