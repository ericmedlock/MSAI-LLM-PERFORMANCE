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
