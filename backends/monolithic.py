"""Monolithic backend: one prompt in, one response out.

The baseline cell. No loop, no delegation, no self-correction. Whatever
internal chain-of-thought the base model does is still a single call, which
is the architectural definition of "monolithic" (documented in the paper).
"""

from __future__ import annotations

import json
import time

from backends.base import Backend, BackendResult, Task
from backends.llm_client import LLMClient
from harness.prompts import PromptSet


class MonolithicBackend(Backend):
    name = "monolithic"

    def __init__(self, client: LLMClient, prompts: PromptSet) -> None:
        self._client = client
        self._system = prompts.monolithic_system

    def run(self, task: Task) -> BackendResult:
        start = time.perf_counter()
        resp = self._client.chat(self._system, task.prompt)
        latency = time.perf_counter() - start
        trace = [
            {"role": "system", "content": self._system},
            {"role": "user", "content": task.prompt},
            {"role": "assistant", "content": resp.text},
        ]
        return BackendResult(
            answer=resp.text,
            latency_s=latency,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            action_count=1,
            raw_trace=json.dumps(trace),
            metadata={"llm_calls": 1},
        )
