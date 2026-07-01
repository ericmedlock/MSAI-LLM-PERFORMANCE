"""The swarm's two defining properties are actually true:
   1. peers run concurrently (real parallelism, not sequential),
   2. peers are independent (controller-free): each sees only the task,
      and each draws with its own seed.
"""

from __future__ import annotations

from backends.base import Task
from backends.swarm import SwarmBackend
from tests.conftest import FakeLLMClient

GSM = Task("gsm8k-001", "gsm8k", "Natalia sold 48 clips...", answer="72")


def test_peers_run_in_parallel_not_sequentially(prompts):
    # each peer call blocks 0.15s; 3 sequential would be ~0.45s. Parallel
    # execution should finish far under the sum.
    client = FakeLLMClient(lambda s, u, seed: "answer 72", delay_s=0.15)
    result = SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    assert result.latency_s < 0.35, f"peers not parallel: {result.latency_s:.3f}s"
    # sum of per-peer latencies is meaningfully larger than wall-clock
    assert result.metadata["parallel_speedup"] > 1.8


def test_each_peer_gets_only_the_task_no_controller(prompts):
    seen_users = []

    def responder(system, user, seed):
        seen_users.append(user)
        return "answer 72"

    client = FakeLLMClient(responder)
    SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    # every peer received exactly the original task prompt -- no peer was fed
    # another peer's output (which would imply orchestration/coordination)
    assert len(seen_users) == 3
    assert all(u == GSM.prompt for u in seen_users)


def test_unparseable_peers_cannot_win_the_vote(prompts):
    # 1 peer gives a real number, 2 ramble with no extractable number.
    # The 2 abstainers must NOT form a winning "" group; the real answer wins.
    answers = {0: "the answer is 72", 1: "hmm let me think about it", 2: "well it depends"}
    client = FakeLLMClient(lambda s, u, seed: answers[seed - 42])
    result = SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    assert result.answer == "the answer is 72"
    assert result.metadata["winning_key"] == "72"
    assert result.metadata["abstained"] == 2
    assert result.metadata["all_abstained"] is False


def test_all_peers_unparseable_flags_coordination_failure(prompts):
    client = FakeLLMClient(lambda s, u, seed: "no idea, sorry")
    result = SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    assert result.metadata["all_abstained"] is True     # visible in analysis
    assert result.metadata["abstained"] == 3
    assert result.metadata["chosen_peer_index"] == 0    # best-effort fallback


def test_peers_use_offset_seeds_for_reproducible_diversity(prompts):
    seeds = []
    client = FakeLLMClient(lambda s, u, seed: (seeds.append(seed) or "answer 72"))
    SwarmBackend(
        client, prompts, num_agents=3, tie_break="lowest_agent_index", base_seed=42
    ).run(GSM)
    assert sorted(seeds) == [42, 43, 44]
