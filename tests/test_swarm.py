"""Exploratory swarm variant knobs (vault: "Swarm Probe Suite — Design", 2026-07-13).

Defaults must reproduce pinned behavior exactly; the knobs are opt-in and every
variant is stamped into row metadata.
"""

from backends.base import Task
from backends.swarm import SwarmBackend
from harness.graders import vote_key, vote_key_ast

BASE_SEED = 42

FN = "def add(x, y):\n    return x + y"
PEER_ANSWERS = {
    BASE_SEED + 0: f"```python\n{FN}  # peer zero\n```",
    BASE_SEED + 1: f"```python\n{FN}  # peer one, different comment\n```",
    BASE_SEED + 2: "```python\ndef add(x, y):\n    return x - y\n```",
}


def test_vote_key_ast_ignores_comments_and_formatting():
    a = "```python\ndef add(x, y):\n    # sum them\n    return x + y\n```"
    b = "```python\ndef add(x, y):\n    return x + y  # other comment\n```"
    c = "```python\ndef add(x, y):\n    return x - y\n```"
    assert vote_key_ast("code", a) == vote_key_ast("code", b)  # comments ignored
    assert vote_key_ast("code", a) != vote_key_ast("code", c)  # semantics kept
    # non-code domains delegate to the exact key
    assert vote_key_ast("math", "answer 7") == vote_key("math", "answer 7")
    # unparseable code falls back to the exact extracted text
    broken = "```python\ndef add(x,:\n```"
    assert vote_key_ast("code", broken) == "def add(x,:"


def test_swarm_exact_vote_treats_comment_variants_as_different(prompts, fake_client_factory):
    client = fake_client_factory(lambda s, u, seed: PEER_ANSWERS[seed])
    b = SwarmBackend(client, prompts, num_agents=3, tie_break="lowest_agent_index",
                     base_seed=BASE_SEED)
    md = b.run(Task("t", "code", "add two numbers")).metadata
    # pinned behavior: three textually distinct programs -> 3-way tie -> peer 0
    assert md["vote_mode"] == "exact" and md["peer_temp"] is None
    assert len(md["vote_counts"]) == 3 and md["tie"] and md["chosen_peer_index"] == 0


def test_swarm_ast_vote_groups_comment_variants(prompts, fake_client_factory):
    client = fake_client_factory(lambda s, u, seed: PEER_ANSWERS[seed])
    b = SwarmBackend(client, prompts, num_agents=3, tie_break="lowest_agent_index",
                     base_seed=BASE_SEED, vote_mode="ast")
    md = b.run(Task("t", "code", "add two numbers")).metadata
    # comment-variants form a genuine 2/3 majority over the semantic outlier
    assert md["vote_mode"] == "ast"
    assert max(md["vote_counts"].values()) == 2
    assert not md["tie"] and md["chosen_peer_index"] == 0


def test_swarm_peer_temperature_passed_and_stamped(prompts, fake_client_factory):
    client = fake_client_factory(lambda s, u, seed: "the answer is 4\n4")
    b = SwarmBackend(client, prompts, num_agents=3, tie_break="lowest_agent_index",
                     base_seed=BASE_SEED, peer_temperature=0.6)
    res = b.run(Task("t", "math", "2+2?", answer="4"))
    assert res.metadata["peer_temp"] == 0.6
    assert [c["temperature"] for c in client.calls] == [0.6, 0.6, 0.6]


def test_swarm_defaults_pass_no_temperature_override(prompts, fake_client_factory):
    client = fake_client_factory(lambda s, u, seed: "the answer is 4\n4")
    b = SwarmBackend(client, prompts, num_agents=3, tie_break="lowest_agent_index",
                     base_seed=BASE_SEED)
    res = b.run(Task("t", "math", "2+2?", answer="4"))
    assert res.metadata["vote_mode"] == "exact"
    assert res.metadata["peer_temp"] is None
    assert all(c["temperature"] is None for c in client.calls)
