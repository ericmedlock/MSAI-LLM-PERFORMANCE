"""Row-completeness assertion for result cells (A40 brief §4).

A cell is COMPLETE iff every (task x backend x trial) combination present in
the manifest/plan has exactly one row. Rows that failed (timeouts ->
``backend_exception``) are counted and reported EXPLICITLY — they are scored
failures, which is fine; what is never fine is a missing row, which reads as
"covered" when it wasn't. Exit code 0 = complete, 1 = incomplete/duplicated.

Usage:
  .venv/bin/python scripts/validate_cell.py RESULTS.jsonl [more.jsonl ...] \
      [--trials 5] [--manifest tasks/frontier_v2_1_manifest.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--manifest", default="tasks/frontier_v2_1_manifest.json")
    args = ap.parse_args()

    from harness.task_loader import load_tasks

    task_ids = {t.task_id for t in load_tasks(args.manifest)}

    rows = []
    for f in args.files:
        rows += [json.loads(l) for l in open(f) if l.strip()]

    backends = sorted({r["backend"] for r in rows})
    seen = Counter()
    for r in rows:
        ts = r.get("trial_seed") or (r.get("metadata") or {}).get("trial_seed")
        seen[(r["task_id"], r["backend"], ts)] += 1

    dupes = {k: c for k, c in seen.items() if c > 1}
    expected = len(task_ids) * len(backends) * args.trials
    missing = []
    trial_seeds = sorted({k[2] for k in seen})
    for t in sorted(task_ids):
        for b in backends:
            for ts in trial_seeds:
                if (t, b, ts) not in seen:
                    missing.append((t, b, ts))

    exc = Counter(r.get("error_category") for r in rows if r.get("error_category"))
    hashes = Counter(r.get("config_hash") for r in rows)
    power = sum(1 for r in rows if (r.get("telemetry") or {}).get("gpu_power_w"))

    print(f"rows: {len(rows)} (expected {expected} = {len(task_ids)} tasks x "
          f"{len(backends)} backends x {args.trials} trials)")
    print(f"trial seeds seen: {trial_seeds}")
    print(f"config hashes: {dict(hashes)}")
    print(f"explicit failures (scored, visible): {dict(exc) or 'none'}")
    print(f"power coverage: {power}/{len(rows)}")
    ok = True
    if len(trial_seeds) != args.trials:
        print(f"FAIL: {len(trial_seeds)} distinct trial seeds, expected {args.trials}")
        ok = False
    if dupes:
        print(f"FAIL: {len(dupes)} duplicated (task,backend,trial) keys, e.g. "
              f"{list(dupes)[:3]}")
        ok = False
    if missing:
        print(f"FAIL: {len(missing)} MISSING rows (silent loss!), e.g. {missing[:5]}")
        ok = False
    if len(rows) != expected:
        print(f"FAIL: row count {len(rows)} != expected {expected}")
        ok = False
    if len(hashes) != 1:
        print("FAIL: mixed config hashes — epochs mixed in one cell")
        ok = False
    print("CELL COMPLETE ✅" if ok else "CELL INCOMPLETE ❌ — do not analyze/merge")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
