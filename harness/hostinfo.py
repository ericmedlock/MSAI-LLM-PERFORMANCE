"""Capture a static host/hardware profile for result provenance.

Per-run telemetry rows record *dynamic* usage (latency, tokens, CPU%, and on
CUDA the GPU VRAM/util/power). The *static* facts — which machine, chip, total
RAM, total GPU VRAM, OS, and which model server/models — don't change during a
run, so we capture them ONCE per run into ``results/host/<env>.json`` rather
than duplicating them onto every row. The row's ``config_hash`` + environment
tie each row back to this profile.

Cross-platform: macOS/Apple Silicon via ``sysctl``/``system_profiler``; NVIDIA
hosts via ``pynvml``. Everything is best-effort — missing fields are ``None``,
never a crash.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import subprocess
from typing import Optional


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip()
    except Exception:
        return ""


def _sysctl(key: str) -> str:
    return _run(["sysctl", "-n", key])


def _macos_hardware() -> dict:
    mem_bytes = _sysctl("hw.memsize")
    total_ram_gb = round(int(mem_bytes) / (1024**3)) if mem_bytes.isdigit() else None
    gpu_cores = None
    gpu_model = None
    disp = _run(["system_profiler", "SPDisplaysDataType"])
    for line in disp.splitlines():
        s = line.strip()
        if s.startswith("Chipset Model:"):
            gpu_model = s.split(":", 1)[1].strip()
        elif s.startswith("Total Number of Cores:") and gpu_cores is None:
            gpu_cores = s.split(":", 1)[1].strip()
    return {
        "chip": _sysctl("machdep.cpu.brand_string") or None,
        "machine_model": _sysctl("hw.model") or None,
        "cpu_cores": int(_sysctl("hw.ncpu")) if _sysctl("hw.ncpu").isdigit() else None,
        "total_ram_gb": total_ram_gb,
        "gpu_model": gpu_model,
        "gpu_cores": gpu_cores,
        "total_vram_gb": total_ram_gb,   # Apple Silicon: unified memory == VRAM
        "unified_memory": True,
    }


def _cuda_hardware() -> dict:
    import psutil

    info: dict = {
        "chip": platform.processor() or None,
        "machine_model": None,
        "cpu_cores": psutil.cpu_count(logical=True),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3)),
        "gpu_model": None,
        "gpu_cores": None,
        "total_vram_gb": None,
        "unified_memory": False,
    }
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(h)
        info["gpu_model"] = name.decode() if isinstance(name, bytes) else name
        info["total_vram_gb"] = round(
            pynvml.nvmlDeviceGetMemoryInfo(h).total / (1024**3)
        )
        info["gpu_count"] = pynvml.nvmlDeviceGetCount()
    except Exception:
        pass
    return info


def _loaded_models(provider: str, base_url: str) -> Optional[list[str]]:
    try:
        import requests

        if provider in ("openai", "openai-compatible", "lmstudio"):
            r = requests.get(f"{base_url.rstrip('/')}/models", timeout=5)
            if r.status_code == 200:
                return [m.get("id") for m in r.json().get("data", [])]
        elif provider == "ollama":
            r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m.get("name") for m in r.json().get("models", [])]
    except Exception:
        return None
    return None


def collect_host_profile(
    *,
    environment: str,
    runtime: str,
    provider: str,
    base_url: str,
    backend_model: str,
    judge_model: str,
    config_hash: str,
    timestamp: str = "",
) -> dict:
    """Gather the full static host/hardware/model profile as a dict."""
    hardware = _macos_hardware() if runtime == "metal" else _cuda_hardware()
    hostname = socket.gethostname()
    host_id = hashlib.sha256(
        f"{hostname}|{hardware.get('chip')}|{hardware.get('total_ram_gb')}".encode()
    ).hexdigest()[:12]
    return {
        "host_id": host_id,
        "hostname": hostname,
        "environment": environment,
        "runtime": runtime,
        "os": platform.platform(),
        "python": platform.python_version(),
        "hardware": hardware,
        "serving": {
            "provider": provider,
            "base_url": base_url,
            "backend_model": backend_model,
            "judge_model": judge_model,
            "models_available": _loaded_models(provider, base_url),
        },
        "config_hash": config_hash,
        "captured_at": timestamp,
    }
