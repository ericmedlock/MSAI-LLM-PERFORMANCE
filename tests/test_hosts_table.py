"""hosts.csv normalization + inline label."""

from __future__ import annotations

import csv

from harness.hostinfo import HOSTS_CSV_COLUMNS, compact_label, profile_to_row, write_hosts_csv

PROFILE = {
    "host_id": "abc123def456", "hostname": "mac", "environment": "local",
    "runtime": "metal", "os": "macOS-26", "python": "3.13",
    "config_hash": "cfg1",
    "hardware": {"chip": "Apple M5 Max", "machine_model": "Mac17,6", "cpu_cores": 18,
                 "total_ram_gb": 48, "gpu_model": "Apple M5 Max", "gpu_cores": "40",
                 "total_vram_gb": 48, "unified_memory": True},
    "serving": {"provider": "openai", "base_url": "u", "backend_model": "deepseek",
                "judge_model": "llama"},
}


def test_compact_label_is_readable():
    assert compact_label(PROFILE) == "Apple M5 Max | 48GB unified | metal"


def test_profile_to_row_has_all_columns():
    row = profile_to_row(PROFILE)
    assert set(row) == set(HOSTS_CSV_COLUMNS)
    assert row["chip"] == "Apple M5 Max" and row["total_vram_gb"] == 48
    assert row["backend_model"] == "deepseek"


def test_write_hosts_csv_dedups_by_host_id(tmp_path):
    path = tmp_path / "hosts.csv"
    write_hosts_csv([PROFILE], path)
    write_hosts_csv([PROFILE], path)  # same host again -> still one row
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 1
    assert rows[0]["host_id"] == "abc123def456"
    assert rows[0]["chip"] == "Apple M5 Max"
