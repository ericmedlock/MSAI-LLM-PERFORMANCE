"""Telemetry collectors: right type per runtime, portable fields present,
Metal GPU-power asymmetry made explicit (None, not fabricated)."""

from __future__ import annotations

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
