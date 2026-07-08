"""Back-fill host_id + host label onto result rows written before hardware
stamping existed (e.g. a run already in progress).

Maps each row to a host profile by environment (results/host/<env>.json), stamps
host_id + host on any row missing them, rewrites the file in place, and refreshes
results/hosts.csv. Idempotent: rows already stamped are left unchanged.

    python scripts/backfill_hardware.py results/local.jsonl
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from harness.hostinfo import compact_label, write_hosts_csv

    argv = argv if argv is not None else sys.argv[1:]
    targets = argv or ["results/local.jsonl"]

    profiles = {}
    for hp in glob.glob("results/host/*.json"):
        p = json.loads(Path(hp).read_text(encoding="utf-8"))
        profiles[p["environment"]] = p
    if not profiles:
        print("no host profiles in results/host/ — run scripts/hardware_snapshot.py first",
              file=sys.stderr)
        return 2

    for target in targets:
        path = Path(target)
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        stamped = 0
        for r in rows:
            if r.get("host_id"):
                continue
            prof = profiles.get(r.get("environment"))
            if not prof:
                continue
            r["host_id"] = prof["host_id"]
            r["host"] = compact_label(prof)
            stamped += 1
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")
        print(f"{target}: stamped {stamped} row(s); {len(rows)} total")

    write_hosts_csv(list(profiles.values()), Path("results/hosts.csv"))
    print(f"refreshed results/hosts.csv ({len(profiles)} host(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
