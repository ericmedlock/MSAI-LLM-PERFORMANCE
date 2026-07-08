"""Agentic backend: sequential Executor + Verifier loop (LangGraph).

Central orchestration, one agent at a time. The executor proposes an answer;
the verifier approves or requests a revision. The loop runs at most
``max_loops`` executor turns (pre-reg S6). This is deliberately sequential —
contrast with the parallel, controller-free swarm.
"""

from __future__ import annotations

import json
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from backends.base import Backend, BackendResult, Task
from backends.llm_client import LLMClient
from harness.prompts import PromptSet


class _State(TypedDict):
    question: str
    candidate: str
    feedback: Optional[str]
    loop: int
    approved: bool
    tokens_in: int
    tokens_out: int
    actions: int
    trace: list[dict]


class AgenticBackend(Backend):
    name = "agentic"

    def __init__(self, client: LLMClient, prompts: PromptSet, max_loops: int) -> None:
        self._client = client
        self._executor_system = prompts.executor_system
        self._verifier_system = prompts.verifier_system
        self._max_loops = max_loops
        self._graph = self._build_graph()

    # -- nodes -------------------------------------------------------------- #
    def _executor(self, state: _State) -> dict:
        user = state["question"]
        if state.get("feedback"):
            user = (
                f"{state['question']}\n\n"
                f"Your previous answer was:\n{state['candidate']}\n\n"
                f"Verifier feedback: {state['feedback']}\n"
                f"Provide a corrected final answer."
            )
        resp = self._client.chat(self._executor_system, user)
        return {
            "candidate": resp.text,
            "loop": state["loop"] + 1,
            "tokens_in": state["tokens_in"] + resp.tokens_in,
            "tokens_out": state["tokens_out"] + resp.tokens_out,
            "actions": state["actions"] + 1,
            "trace": state["trace"]
            + [{"agent": "executor", "user": user, "output": resp.text}],
        }

    def _verifier(self, state: _State) -> dict:
        user = (
            f"Task:\n{state['question']}\n\n"
            f"Candidate answer:\n{state['candidate']}"
        )
        resp = self._client.chat(self._verifier_system, user)
        approved = resp.text.strip().upper().startswith("APPROVE")
        feedback = None if approved else resp.text.strip()
        return {
            "approved": approved,
            "feedback": feedback,
            "tokens_in": state["tokens_in"] + resp.tokens_in,
            "tokens_out": state["tokens_out"] + resp.tokens_out,
            "actions": state["actions"] + 1,
            "trace": state["trace"]
            + [{"agent": "verifier", "output": resp.text, "approved": approved}],
        }

    def _route(self, state: _State) -> str:
        if state["approved"] or state["loop"] >= self._max_loops:
            return END
        return "executor"

    def _build_graph(self):
        g = StateGraph(_State)
        g.add_node("executor", self._executor)
        g.add_node("verifier", self._verifier)
        g.add_edge(START, "executor")
        g.add_edge("executor", "verifier")
        g.add_conditional_edges("verifier", self._route, {"executor": "executor", END: END})
        return g.compile()

    # -- Backend API -------------------------------------------------------- #
    def run(self, task: Task) -> BackendResult:
        init: _State = {
            "question": task.prompt,
            "candidate": "",
            "feedback": None,
            "loop": 0,
            "approved": False,
            "tokens_in": 0,
            "tokens_out": 0,
            "actions": 0,
            "trace": [],
        }
        start = time.perf_counter()
        final = self._graph.invoke(init)
        latency = time.perf_counter() - start
        return BackendResult(
            answer=final["candidate"],
            latency_s=latency,
            tokens_in=final["tokens_in"],
            tokens_out=final["tokens_out"],
            action_count=final["actions"],
            raw_trace=json.dumps(final["trace"]),
            metadata={
                "executor_loops": final["loop"],
                "verifier_approved": final["approved"],
                "llm_calls": final["actions"],
            },
        )
