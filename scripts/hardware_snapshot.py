"""Capture the host/hardware/model profile for the active environment.

Writes results/host/<env>.json. The runner also does this automatically at the
start of every run; this script is for capturing it on demand (e.g. for a run
already in progress, since hardware is constant during a run).

    python scripts/hardware_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from harness.config import load_config, load_dotenv
    from harness.hostinfo import collect_host_profile

    load_dotenv()
    config = load_config(ROOT / "config" / "config.yaml")
    env = config.env().resolved()
    profile = collect_host_profile(
        environment=env.key,
        runtime=env.runtime,
        provider=env.provider,
        base_url=env.base_url,
        backend_model=env.model,
        judge_model=config.judge.model,
        config_hash=config.config_hash,
    )
    out = Path(config.results_dir) / "host" / f"{env.key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(json.dumps(profile, indent=2))
    print(f"\nWrote -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
