"""LLM client abstraction.

All backends call the model through the :class:`LLMClient` protocol, never
through Ollama directly. This keeps decoding parameters pinned in exactly
one place and lets tests inject a deterministic fake with no network or GPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import requests


@dataclass(frozen=True)
class LLMResponse:
    """One model turn plus the token accounting the harness needs."""

    text: str
    tokens_in: int
    tokens_out: int


@runtime_checkable
class LLMClient(Protocol):
    """The single method every backend uses to talk to the model."""

    def chat(
        self, system: str, user: str, *, seed: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Return one model turn. ``seed`` overrides the pinned seed when set;
        ``temperature`` overrides the pinned temperature when set (EXPLORATORY
        swarm variants only — pinned cells never pass it)
        (used by swarm peers to draw diverse-but-reproducible samples)."""
        ...


class OllamaClient:
    """Thin, pinned wrapper over the Ollama ``/api/chat`` endpoint.

    Every decoding knob that must be held constant across cells
    (temperature, context window, max output tokens, seed) is fixed at
    construction time from config -- backends cannot override them.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        model_tag: str,
        temperature: float,
        num_ctx: int,
        max_tokens: int,
        seed: int,
        timeout_s: float = 600.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_tag = model_tag
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_tokens = max_tokens
        self.seed = seed
        self.timeout_s = timeout_s

    def chat(
        self, system: str, user: str, *, seed: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        payload = {
            "model": self.model_tag,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.max_tokens,
                "seed": self.seed if seed is None else seed,
            },
        }
        resp = requests.post(
            f"{self.endpoint}/api/chat", json=payload, timeout=self.timeout_s
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        return LLMResponse(
            text=text,
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
        )

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False


class OpenAICompatibleClient:
    """Client for OpenAI-compatible servers: LM Studio, vLLM, llama.cpp, etc.

    LM Studio serves ``POST {base_url}/chat/completions`` where ``base_url``
    already ends in ``/v1`` (e.g. ``http://localhost:1234/v1``). Token counts
    come from the ``usage`` block.

    Note on context window: the OpenAI chat API has no per-request context
    size. For this provider ``num_ctx`` is a *recorded* pin, not an enforced
    one -- set the context length when you load the model in LM Studio so it
    matches ``config.decoding.num_ctx``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model_tag: str,
        temperature: float,
        num_ctx: int,
        max_tokens: int,
        seed: int,
        api_key: str = "lm-studio",
        timeout_s: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_tag = model_tag
        self.temperature = temperature
        self.num_ctx = num_ctx  # recorded only; see class docstring
        self.max_tokens = max_tokens
        self.seed = seed
        self.api_key = api_key
        self.timeout_s = timeout_s

    def chat(
        self, system: str, user: str, *, seed: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        payload = {
            "model": self.model_tag,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed if seed is None else seed,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/models", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False
