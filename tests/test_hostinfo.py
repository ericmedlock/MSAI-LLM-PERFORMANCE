"""Host/hardware profile capture: structure + deterministic host_id."""

from __future__ import annotations

import harness.hostinfo as hostinfo
from harness.hostinfo import collect_host_profile


def _profile(monkeypatch, runtime="metal"):
    # never touch the network for models_available in tests
    monkeypatch.setattr(hostinfo, "_loaded_models", lambda provider, base_url: ["m1", "m2"])
    return collect_host_profile(
        environment="local", runtime=runtime, provider="openai",
        base_url="http://localhost:1234/v1", backend_model="deepseek-r1-distill-qwen-14b",
        judge_model="llama-3.2-3b-instruct", config_hash="abc123", timestamp="t0",
    )


def test_profile_has_required_sections(monkeypatch):
    p = _profile(monkeypatch)
    assert set(p) >= {"host_id", "hostname", "hardware", "serving", "config_hash", "runtime"}
    for k in ("chip", "total_ram_gb", "gpu_model", "total_vram_gb", "unified_memory"):
        assert k in p["hardware"]
    assert p["serving"]["backend_model"] == "deepseek-r1-distill-qwen-14b"
    assert p["serving"]["judge_model"] == "llama-3.2-3b-instruct"
    assert p["serving"]["models_available"] == ["m1", "m2"]
    assert p["config_hash"] == "abc123"


def test_host_id_is_stable_12_hex(monkeypatch):
    p1 = _profile(monkeypatch)
    p2 = _profile(monkeypatch)
    assert p1["host_id"] == p2["host_id"]
    assert len(p1["host_id"]) == 12
    int(p1["host_id"], 16)  # hex


def test_cuda_runtime_takes_nvidia_branch(monkeypatch):
    # cuda branch uses psutil + (optional) pynvml; must not crash without a GPU
    p = _profile(monkeypatch, runtime="cuda")
    assert p["hardware"]["unified_memory"] is False
    assert "total_ram_gb" in p["hardware"]
