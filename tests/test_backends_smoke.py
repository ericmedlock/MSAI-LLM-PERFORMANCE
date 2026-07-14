"""Offline smoke tests: every backend runs once against the fake model and
returns a well-formed BackendResult. No real model is contacted."""

from __future__ import annotations

from backends.agentic import AgenticBackend
from backends.base import BackendResult, Task
from backends.monolithic import MonolithicBackend
from backends.swarm import SwarmBackend
from tests.conftest import FakeLLMClient

GSM = Task("gsm8k-001", "gsm8k", "Natalia sold 48 clips...", answer="72")


def _assert_wellformed(result: BackendResult):
    assert isinstance(result, BackendResult)
    assert result.answer
    assert result.latency_s >= 0
    assert result.tokens_in > 0 and result.tokens_out > 0
    assert result.action_count >= 1
    assert result.raw_trace  # JSON transcript present


def test_monolithic_single_call(prompts):
    client = FakeLLMClient(lambda s, u, seed: "reasoning... 72")
    result = MonolithicBackend(client, prompts).run(GSM)
    _assert_wellformed(result)
    assert result.action_count == 1
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == prompts.monolithic_system


def test_agentic_stops_when_verifier_approves(prompts):
    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "APPROVE"
        return "the answer is 72"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2).run(GSM)
    _assert_wellformed(result)
    # one executor + one verifier, then stop
    assert result.metadata["executor_loops"] == 1
    assert result.metadata["verifier_approved"] is True
    assert result.action_count == 2


def test_agentic_respects_max_loops_when_never_approved(prompts):
    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "REVISE: still wrong"
        return "attempted answer 70"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2).run(GSM)
    # executor runs exactly max_loops times; never exceeds the cap
    assert result.metadata["executor_loops"] == 2
    assert result.metadata["verifier_approved"] is False
    # 2 executor + 2 verifier calls
    assert result.action_count == 4


def test_agentic_strict_misses_prose_buried_approve(prompts):
    """Pinned behavior (the 'false revision', engineering log §8): a verdict
    that does not START with APPROVE parses as a revision request."""

    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "The candidate answer is correct. APPROVE\n\n$\\boxed{70}$"
        return "the answer is 70"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2).run(GSM)
    assert result.metadata["verifier_approved"] is False
    assert result.metadata["verdict_mode"] == "strict"
    assert result.metadata["executor_loops"] == 2  # forced extra loop


def test_agentic_lenient_hears_prose_buried_approve(prompts):
    """AGENTIC 2.0 (Amendment 2026-07-14): the last standalone APPROVE/REVISE
    token decides, so the same prose-buried approval stops the loop."""

    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "The candidate answer is correct. APPROVE\n\n$\\boxed{70}$"
        return "the answer is 70"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2, verdict_mode="lenient").run(GSM)
    assert result.metadata["verifier_approved"] is True
    assert result.metadata["verdict_mode"] == "lenient"
    assert result.metadata["executor_loops"] == 1  # no false revision
    assert result.action_count == 2


def test_agentic_lenient_last_token_decides(prompts):
    # APPROVE appears first but the verifier's final verdict is REVISE
    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "I considered APPROVE at first, but the sum is wrong. REVISE"
        return "attempted answer 70"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2, verdict_mode="lenient").run(GSM)
    assert result.metadata["verifier_approved"] is False


def test_agentic_lenient_neither_token_means_revise(prompts):
    # Chain-of-thought fallback text (no verdict token at all) must not approve;
    # 'APPROVED' must not match the standalone APPROVE token either.
    def responder(system, user, seed):
        if system == prompts.verifier_system:
            return "Okay, so I need to check whether 48 clips... this looks APPROVED-ish"
        return "attempted answer 70"

    client = FakeLLMClient(responder)
    result = AgenticBackend(client, prompts, max_loops=2, verdict_mode="lenient").run(GSM)
    assert result.metadata["verifier_approved"] is False


def test_swarm_dispatches_num_agents_and_majority_votes(prompts):
    # two peers say 72, one says 5 -> majority 72
    answers = {0: "final 72", 1: "final 72", 2: "final 5"}
    client = FakeLLMClient(lambda s, u, seed: answers[seed - 42])
    result = SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    _assert_wellformed(result)
    assert result.action_count == 3
    assert result.metadata["num_agents"] == 3
    assert result.metadata["vote_counts"]["72"] == 2
    assert result.metadata["winning_key"] == "72"
    assert result.metadata["tie"] is False


def test_swarm_tie_breaks_on_lowest_agent_index(prompts):
    # all distinct -> 3-way tie -> lowest_agent_index picks peer 0's answer
    answers = {0: "answer 72", 1: "answer 5", 2: "answer 3"}
    client = FakeLLMClient(lambda s, u, seed: answers[seed - 42])
    result = SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    assert result.metadata["tie"] is True
    assert result.metadata["chosen_peer_index"] == 0
    assert result.answer == "answer 72"
