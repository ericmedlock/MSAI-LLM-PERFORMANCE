"""Telemetry collectors: right type per runtime, portable fields present,
Metal GPU-power asymmetry made explicit (None, not fabricated), and NVML
device selection honoring CUDA_VISIBLE_DEVICES (shared multi-GPU nodes)."""

from __future__ import annotations

import harness.telemetry as telemetry
from harness.telemetry import (
    CudaCollector,
    MetalCollector,
    NoopCollector,
    _SamplingCollector,
    make_collector,
)


def test_factory_selects_collector_by_runtime():
    assert isinstance(make_collector("metal"), MetalCollector)
    assert isinstance(make_collector("cuda"), CudaCollector)
    assert isinstance(make_collector("cpu"), _SamplingCollector)


def test_sampling_collector_reports_portable_fields():
    c = make_collector("cpu", interval_s=0.01)
    c.start()
    sum(range(100_000))  # a little work to sample
    result = c.stop()
    assert result["peak_ram_mb"] > 0
    assert "avg_cpu_pct" in result
    assert result["samples"] >= 0


def test_metal_leaves_gpu_power_none_by_design():
    c = MetalCollector(interval_s=0.01)
    c.start()
    result = c.stop()
    assert result["runtime"] == "metal"
    assert result["gpu_power_w"] is None      # requires sudo powermetrics; omitted
    assert result["peak_vram_mb"] is None


def test_noop_collector_records_nothing():
    c = NoopCollector()
    c.start()
    assert c.stop() == {}


class _Mem:
    used = 4 * 1024 * 1024 * 1024  # 4 GiB


class _Util:
    gpu = 87


class _FakeNvml:
    """Just enough NVML to drive CudaCollector on a GPU-less machine."""

    def nvmlInit(self):
        pass

    def nvmlDeviceGetHandleByIndex(self, index):
        return ("by-index", index)

    def nvmlDeviceGetHandleByUUID(self, uuid):
        return ("by-uuid", uuid)

    def nvmlDeviceGetName(self, handle):
        return b"NVIDIA A40"  # bytes: the older-pynvml shape

    def nvmlDeviceGetUUID(self, handle):
        return f"GPU-fake-{handle[1]}"

    def nvmlDeviceGetMemoryInfo(self, handle):
        return _Mem()

    def nvmlDeviceGetUtilizationRates(self, handle):
        return _Util()

    def nvmlDeviceGetPowerUsage(self, handle):
        return 250_000  # milliwatts


def _with_fake_nvml(monkeypatch):
    monkeypatch.setattr(telemetry, "pynvml", _FakeNvml(), raising=False)
    monkeypatch.setattr(telemetry, "_HAS_NVML", True)


def test_nvml_handle_defaults_to_index_0_without_visible_devices(monkeypatch):
    _with_fake_nvml(monkeypatch)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    assert telemetry._resolve_nvml_handle() == ("by-index", 0)


def test_nvml_handle_honors_cuda_visible_devices_index(monkeypatch):
    # A SLURM job allocated physical GPU 2 of a 4-GPU node must sample
    # GPU 2, not GPU 0 (which may belong to another job).
    _with_fake_nvml(monkeypatch)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,3")
    assert telemetry._resolve_nvml_handle() == ("by-index", 2)


def test_nvml_handle_honors_cuda_visible_devices_uuid(monkeypatch):
    _with_fake_nvml(monkeypatch)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-deadbeef")
    assert telemetry._resolve_nvml_handle() == ("by-uuid", "GPU-deadbeef")


def test_nvml_handle_none_when_no_gpu_visible(monkeypatch):
    _with_fake_nvml(monkeypatch)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    assert telemetry._resolve_nvml_handle() is None


def test_cuda_collector_samples_allocated_gpu_and_stamps_identity(monkeypatch):
    _with_fake_nvml(monkeypatch)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    c = CudaCollector(interval_s=0.01)
    c.start()
    sum(range(100_000))
    result = c.stop()
    assert result["runtime"] == "cuda"
    assert result["peak_vram_mb"] == 4096.0
    assert result["avg_gpu_util_pct"] == 87.0
    assert result["gpu_power_w"] == 250.0
    assert result["gpu_name"] == "NVIDIA A40"
    assert result["gpu_uuid"] == "GPU-fake-1"  # device 1, not device 0


def test_cuda_collector_degrades_to_none_without_nvml(monkeypatch):
    monkeypatch.setattr(telemetry, "_HAS_NVML", False)
    c = CudaCollector(interval_s=0.01)
    c.start()
    result = c.stop()
    assert result["peak_vram_mb"] is None
    assert result["avg_gpu_util_pct"] is None
    assert result["gpu_power_w"] is None
