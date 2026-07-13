"""External hardware/resource telemetry, collected by the harness.

Backends never self-report resource use. The harness wraps each ``run()``
call, samples the system in a background thread, and records peak/average
figures on the telemetry row.

Cross-environment reality (pre-reg S12, Metal-vs-CUDA threat):
- CPU% and system RAM are portable (psutil) on both Metal and CUDA.
- GPU VRAM / util / power are available on CUDA via NVML (``pynvml``).
- On Apple Silicon (Metal) there is **no** ``nvidia-smi``/NVML. GPU power
  needs ``sudo powermetrics`` and is intentionally left out of the harness;
  those fields are ``None`` on Metal and this asymmetry is a documented
  limitation, not a bug. On unified memory the model still shows up in
  system RAM, so ``peak_ram_mb`` remains a meaningful footprint proxy.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional, Protocol

import psutil

try:  # NVML is only present on NVIDIA/CUDA hosts (Azure cloud cell)
    import pynvml  # type: ignore

    _HAS_NVML = True
except Exception:  # pragma: no cover - platform dependent
    _HAS_NVML = False


def _nvml_str(value) -> str:
    """NVML string returns are bytes on older pynvml, str on newer."""
    return value.decode() if isinstance(value, bytes) else str(value)


def _resolve_nvml_handle():
    """Resolve the NVML handle for THIS process's allocated GPU.

    NVML enumerates physical devices and ignores ``CUDA_VISIBLE_DEVICES``,
    so on a shared multi-GPU node (e.g. a SLURM job given GPU 2 of 4)
    index 0 may be another job's GPU. Honor the first entry of
    ``CUDA_VISIBLE_DEVICES`` — an index, ``GPU-<uuid>``, or ``MIG-<uuid>``
    — before falling back to index 0 (single-GPU hosts, or cgroup-isolated
    nodes where NVML already sees only ours). Returns None when no GPU is
    visible or resolution fails; callers degrade to the no-NVML path.
    """
    try:
        visible = os.environ.get("CUDA_VISIBLE_DEVICES")
        if visible is not None:
            first = visible.split(",")[0].strip()
            if first == "" or first == "-1":  # explicitly no GPU
                return None
            if first.startswith(("GPU-", "MIG-")):
                try:
                    return pynvml.nvmlDeviceGetHandleByUUID(first)
                except TypeError:  # older pynvml wants bytes
                    return pynvml.nvmlDeviceGetHandleByUUID(first.encode())
            return pynvml.nvmlDeviceGetHandleByIndex(int(first))
        return pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception:  # pragma: no cover - depends on host GPU state
        return None


class TelemetryCollector(Protocol):
    def start(self) -> None: ...
    def stop(self) -> dict: ...


class NoopCollector:
    """Used in tests: records nothing, imposes no sampling overhead."""

    def start(self) -> None:  # noqa: D401
        pass

    def stop(self) -> dict:
        return {}


class _SamplingCollector:
    """Base collector that polls CPU/RAM in a background thread."""

    runtime = "cpu"

    def __init__(self, interval_s: float = 0.1) -> None:
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc = psutil.Process()
        self._peak_ram_mb = 0.0
        self._peak_sys_used_mb = 0.0
        self._cpu_samples: list[float] = []
        self._extra_start()

    # hooks for GPU-capable subclasses
    def _extra_start(self) -> None:
        pass

    def _extra_sample(self) -> None:
        pass

    def _extra_result(self) -> dict:
        return {}

    def _sample(self) -> None:
        while not self._stop.is_set():
            rss_mb = self._proc.memory_info().rss / (1024 * 1024)
            self._peak_ram_mb = max(self._peak_ram_mb, rss_mb)
            # System-wide memory: with an out-of-process model server (LM Studio),
            # the model's footprint is NOT in this harness's RSS, so we also track
            # whole-system used memory to reflect the real footprint.
            self._peak_sys_used_mb = max(
                self._peak_sys_used_mb, psutil.virtual_memory().used / (1024 * 1024)
            )
            self._cpu_samples.append(psutil.cpu_percent(interval=None))
            self._extra_sample()
            time.sleep(self._interval)

    def start(self) -> None:
        psutil.cpu_percent(interval=None)  # prime the counter
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        avg_cpu = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else None
        result = {
            "runtime": self.runtime,
            "peak_ram_mb": round(self._peak_ram_mb, 1),          # harness process only
            "peak_sys_used_mb": round(self._peak_sys_used_mb, 1),  # whole system (incl. model server)
            "avg_cpu_pct": round(avg_cpu, 1) if avg_cpu is not None else None,
            "samples": len(self._cpu_samples),
        }
        result.update(self._extra_result())
        return result


class MetalCollector(_SamplingCollector):
    """Apple Silicon. GPU power/util require sudo and are left as None."""

    runtime = "metal"

    def _extra_result(self) -> dict:
        return {"peak_vram_mb": None, "avg_gpu_util_pct": None, "gpu_power_w": None}


class CudaCollector(_SamplingCollector):
    """NVIDIA/CUDA. Peak VRAM, GPU utilization and power via NVML."""

    runtime = "cuda"

    def _extra_start(self) -> None:
        self._peak_vram_mb = 0.0
        self._gpu_util: list[float] = []
        self._gpu_power: list[float] = []
        self._handle = None
        self._gpu_name: Optional[str] = None
        self._gpu_uuid: Optional[str] = None
        if _HAS_NVML:
            pynvml.nvmlInit()
            self._handle = _resolve_nvml_handle()
        if self._handle:
            # Stamp the sampled device's identity so rows prove which GPU
            # they were measured on (cell-homogeneity check on shared nodes).
            try:
                self._gpu_name = _nvml_str(pynvml.nvmlDeviceGetName(self._handle))
                self._gpu_uuid = _nvml_str(pynvml.nvmlDeviceGetUUID(self._handle))
            except Exception:  # pragma: no cover - depends on host GPU state
                pass

    def _extra_sample(self) -> None:
        if not self._handle:
            return
        mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
        self._peak_vram_mb = max(self._peak_vram_mb, mem.used / (1024 * 1024))
        self._gpu_util.append(pynvml.nvmlDeviceGetUtilizationRates(self._handle).gpu)
        try:
            self._gpu_power.append(pynvml.nvmlDeviceGetPowerUsage(self._handle) / 1000.0)
        except Exception:  # pragma: no cover - some datacenter GPUs restrict this
            pass

    def _extra_result(self) -> dict:
        if not self._handle:
            return {"peak_vram_mb": None, "avg_gpu_util_pct": None, "gpu_power_w": None}
        avg_util = sum(self._gpu_util) / len(self._gpu_util) if self._gpu_util else None
        avg_power = sum(self._gpu_power) / len(self._gpu_power) if self._gpu_power else None
        return {
            "peak_vram_mb": round(self._peak_vram_mb, 1),
            "avg_gpu_util_pct": round(avg_util, 1) if avg_util is not None else None,
            "gpu_power_w": round(avg_power, 1) if avg_power is not None else None,
            "gpu_name": self._gpu_name,
            "gpu_uuid": self._gpu_uuid,
        }


def make_collector(runtime: str, *, interval_s: float = 0.1) -> TelemetryCollector:
    """Factory keyed on the environment's runtime (from config, not code)."""
    if runtime == "cuda":
        return CudaCollector(interval_s=interval_s)
    if runtime == "metal":
        return MetalCollector(interval_s=interval_s)
    return _SamplingCollector(interval_s=interval_s)
