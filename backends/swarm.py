"""Swarm backend: N peers in parallel, no central controller, majority vote.

Design commitments (pre-reg S6, and the build brief):
- The peers fan out from START as independent LangGraph nodes. No node
  decides what another peer does -> there is no orchestrator/controller.
- They run **concurrently for real**: each peer node is async and runs its
  (blocking) model call in a worker thread, so the graph awaits all peers
  at once. Wall-clock ~ slowest peer, not the sum. This is verified in
  metadata (`wall_s` vs `peer_latencies_s`), never assumed.
- Aggregation is a pure majority vote over a domain-appropriate vote key,
  with a fixed tie-break (``lowest_agent_index``). The aggregator does no
  reasoning and calls no model.

Independent-sample seeding (pre-reg Amendment Log, 2026-07-01): the
pre-registration (S2) treats the swarm as aggregating *independent samples*
by majority vote. Under the pinned temperature 0.0 a single shared seed makes
all peers deterministically identical, so the vote would be degenerate and
that premise would not hold. Peers therefore draw with
``seed = base_seed + peer_index`` (``swarm.peer_seed_strategy: offset`` in
config) -- diverse yet fully reproducible. ``same`` restores the shared seed.
"""

from __future__ import annotations

import asyncio
import json
import operator
import time
from collections import Counter
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from backends.base import Backend, BackendResult, Task
from backends.llm_client import LLMClient
from harness.graders import vote_key
from harness.prompts import PromptSet


class _PeerOut(TypedDict):
    index: int
    answer: str
    tokens_in: int
    tokens_out: int
    latency_s: float


class _State(TypedDict):
    question: str
    domain: str
    peers: Annotated[list[_PeerOut], operator.add]


class SwarmBackend(Backend):
    name = "swarm"

    def __init__(
        self,
        client: LLMClient,
        prompts: PromptSet,
        *,
        num_agents: int,
        tie_break: str,
        base_seed: int,
        peer_seed_strategy: str = "offset",
    ) -> None:
        self._client = client
        self._peer_system = prompts.peer_system
        self._num_agents = num_agents
        self._tie_break = tie_break
        self._base_seed = base_seed
        self._peer_seed_strategy = peer_seed_strategy
        self._graph = self._build_graph()

    def _peer_seed(self, index: int) -> int:
        if self._peer_seed_strategy == "same":
            return self._base_seed
        return self._base_seed + index

    def _make_peer_node(self, index: int):
        async def peer(state: _State) -> dict:
            t0 = time.perf_counter()
            resp = await asyncio.to_thread(
                self._client.chat,
                self._peer_system,
                state["question"],
                seed=self._peer_seed(index),
            )
            return {
                "peers": [
                    _PeerOut(
                        index=index,
                        answer=resp.text,
                        tokens_in=resp.tokens_in,
                        tokens_out=resp.tokens_out,
                        latency_s=time.perf_counter() - t0,
                    )
                ]
            }

        return peer

    def _aggregate(self, state: _State) -> dict:
        # No-op node: aggregation happens in run() where we have timing.
        return {}

    def _build_graph(self):
        g = StateGraph(_State)
        for i in range(self._num_agents):
            node = f"peer_{i}"
            g.add_node(node, self._make_peer_node(i))
            g.add_edge(START, node)       # fan-out: independent peers
            g.add_edge(node, "aggregate")  # fan-in
        g.add_node("aggregate", self._aggregate)
        g.add_edge("aggregate", END)
        return g.compile()

    def _majority_vote(self, domain: str, peers: list[_PeerOut]) -> tuple[str, dict]:
        ordered = sorted(peers, key=lambda p: p["index"])  # deterministic
        keys = [vote_key(domain, p["answer"]) for p in ordered]
        # A peer whose answer has no extractable value (empty vote key) ABSTAINS:
        # it must not be able to win the vote. Otherwise all unparseable peers
        # collapse into one "" group that can outnumber the real answers and the
        # swarm would return garbage over a genuine majority.
        valid = [(p, k) for p, k in zip(ordered, keys) if k != ""]
        counts = Counter(k for _, k in valid)
        if counts:
            top = max(counts.values())
            winners = {k for k, c in counts.items() if c == top}
            # tie-break: lowest_agent_index -> earliest VALID peer in a winning group
            chosen = next(p for p, k in valid if k in winners)
            all_abstained = False
        else:
            # every peer failed to produce a parseable answer -> best effort,
            # flagged so it is visible in analysis (a coordination/format failure)
            chosen = ordered[0]
            winners = set()
            all_abstained = True
        return chosen["answer"], {
            "vote_counts": dict(counts),
            "abstained": sum(1 for k in keys if k == ""),
            "all_abstained": all_abstained,
            "winning_key": vote_key(domain, chosen["answer"]),
            "tie": len(winners) > 1,
            "chosen_peer_index": chosen["index"],
        }

    def run(self, task: Task) -> BackendResult:
        init: _State = {"question": task.prompt, "domain": task.domain, "peers": []}
        start = time.perf_counter()
        final = asyncio.run(self._graph.ainvoke(init))
        wall = time.perf_counter() - start

        peers: list[_PeerOut] = final["peers"]
        answer, vote_meta = self._majority_vote(task.domain, peers)
        peer_latencies = [p["latency_s"] for p in sorted(peers, key=lambda p: p["index"])]

        return BackendResult(
            answer=answer,
            latency_s=wall,
            tokens_in=sum(p["tokens_in"] for p in peers),
            tokens_out=sum(p["tokens_out"] for p in peers),
            action_count=len(peers),
            raw_trace=json.dumps(sorted(peers, key=lambda p: p["index"])),
            metadata={
                "num_agents": self._num_agents,
                "peer_seed_strategy": self._peer_seed_strategy,
                "wall_s": wall,
                "peer_latencies_s": peer_latencies,
                "parallel_speedup": (sum(peer_latencies) / wall) if wall > 0 else None,
                "llm_calls": len(peers),
                **vote_meta,
            },
        )
