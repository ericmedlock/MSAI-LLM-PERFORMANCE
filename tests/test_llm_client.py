"""Unit tests for the HTTP clients, with `requests` mocked (no live server)."""

from __future__ import annotations

from types import SimpleNamespace

import backends.llm_client as llm
from backends.llm_client import OllamaClient, OpenAICompatibleClient


def _fake_post(captured):
    def post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: captured["response"],
        )

    return post


def test_openai_client_builds_request_and_parses_usage(monkeypatch):
    captured = {
        "response": {
            "choices": [{"message": {"content": "final 72"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 46, "completion_tokens": 219},
        }
    }
    monkeypatch.setattr(llm.requests, "post", _fake_post(captured))
    client = OpenAICompatibleClient(
        base_url="http://localhost:1234/v1",
        model_tag="deepseek-r1-distill-qwen-14b",
        temperature=0.0, num_ctx=8192, max_tokens=2048, seed=42, api_key="lm-studio",
    )
    resp = client.chat("sys", "hello", seed=99)

    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["json"]["model"] == "deepseek-r1-distill-qwen-14b"
    assert captured["json"]["temperature"] == 0.0
    assert captured["json"]["seed"] == 99                      # per-call override wins
    assert captured["headers"]["Authorization"] == "Bearer lm-studio"
    assert resp.text == "final 72"
    assert resp.tokens_in == 46 and resp.tokens_out == 219


def test_ollama_client_builds_request_and_parses_counts(monkeypatch):
    captured = {
        "response": {
            "message": {"content": "final 72"},
            "prompt_eval_count": 30,
            "eval_count": 120,
        }
    }
    monkeypatch.setattr(llm.requests, "post", _fake_post(captured))
    client = OllamaClient(
        endpoint="http://localhost:11434",
        model_tag="deepseek-r1:14b",
        temperature=0.0, num_ctx=8192, max_tokens=2048, seed=42,
    )
    resp = client.chat("sys", "hello")

    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["options"]["seed"] == 42
    assert captured["json"]["options"]["num_ctx"] == 8192
    assert resp.tokens_in == 30 and resp.tokens_out == 120


def test_integration_reachability_probe_is_provider_correct(monkeypatch):
    # Regression: the live-server probe must hit Ollama's /api/tags (Ollama has
    # NO /models). A /models-only probe 404'd on a *live* Ollama and silently
    # skipped the integration tests against it. Guarded here in the OFFLINE
    # suite because the integration tests themselves skip when no server is up.
    from tests.test_integration_lmstudio import _reachable

    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(llm.requests, "get", fake_get)
    assert _reachable(SimpleNamespace(provider="ollama", base_url="http://h:11434"))
    assert _reachable(SimpleNamespace(provider="openai", base_url="http://h:1234/v1"))
    assert calls == ["http://h:11434/api/tags", "http://h:1234/v1/models"]

    def boom(url, timeout=None):
        raise ConnectionError("server down")

    monkeypatch.setattr(llm.requests, "get", boom)
    assert _reachable(SimpleNamespace(provider="ollama", base_url="http://h:11434")) is False


# -- transport retry hardening (A40 brief §4, 2026-07-21) -------------------- #
def _flaky_post(script, captured_sleeps):
    """Return a fake requests.post that plays through `script` — each entry is
    an Exception instance to raise or an int status code to return."""
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None, headers=None):
        step = script[calls["n"]]
        calls["n"] += 1
        if isinstance(step, Exception):
            raise step

        class R:
            status_code = step
            def raise_for_status(self):
                pass
            def json(self):
                return {"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 2}
        return R()

    return fake_post, calls


def _client():
    return OllamaClient(endpoint="http://x", model_tag="m",
                        temperature=0.6, num_ctx=8192, max_tokens=6144, seed=42)


def test_retry_recovers_from_transient_connection_errors(monkeypatch):
    sleeps = []
    fake, calls = _flaky_post(
        [llm.requests.ConnectionError(), llm.requests.ConnectionError(), 200], sleeps)
    monkeypatch.setattr(llm.requests, "post", fake)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    assert _client().chat("s", "u").text == "ok"
    assert calls["n"] == 3 and sleeps == [5.0, 15.0]


def test_retry_recovers_from_one_timeout_but_not_two(monkeypatch):
    sleeps = []
    fake, calls = _flaky_post([llm.requests.Timeout(), 200], sleeps)
    monkeypatch.setattr(llm.requests, "post", fake)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    assert _client().chat("s", "u").text == "ok"      # one timeout: retried

    fake2, _ = _flaky_post([llm.requests.Timeout(), llm.requests.Timeout()], sleeps)
    monkeypatch.setattr(llm.requests, "post", fake2)
    import pytest
    with pytest.raises(llm.requests.Timeout):          # second timeout: raises,
        _client().chat("s", "u")                       # runner records the row


def test_retry_recovers_from_transient_5xx(monkeypatch):
    sleeps = []
    fake, calls = _flaky_post([503, 200], sleeps)
    monkeypatch.setattr(llm.requests, "post", fake)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    assert _client().chat("s", "u").text == "ok"
    assert calls["n"] == 2
