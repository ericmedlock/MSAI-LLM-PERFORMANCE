"""Record an environment snapshot for reproducibility.

Run before every experiment session and commit the output alongside the
results:  python scripts/env_snapshot.py > results/env_<env>_<date>.json

Captures OS, Python, package versions, the resolved config hash, and the
pinned Ollama model digest (if the server is reachable) so any result set
can be tied back to the exact stack that produced it.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _pip_freeze() -> list[str]:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.splitlines()
    except Exception:
        return []


def _ollama_model_digest(endpoint: str, tag: str) -> str | None:
    try:
        import requests

        resp = requests.post(f"{endpoint}/api/show", json={"name": tag}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("details", {}).get("digest") or data.get("digest")
    except Exception:
        return None
    return None


def main() -> int:
    from harness.config import load_config

    config = load_config(ROOT / "config" / "config.yaml")
    env = config.env()
    snapshot = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": sys.version,
        "active_environment": config.active_environment,
        "environment_name": env.name,
        "runtime": env.runtime,
        "model_tag": config.model.tag,
        "model_quantization": config.model.quantization,
        "model_digest_pinned": config.model.digest or None,
        "model_digest_live": _ollama_model_digest(env.ollama_endpoint, config.model.tag),
        "config_hash": config.config_hash,
        "pip_freeze": _pip_freeze(),
    }
    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
