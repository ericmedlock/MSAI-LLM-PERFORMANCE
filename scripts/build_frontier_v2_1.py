"""Build tasks/frontier_v2_1_manifest.json — v2.1 re-sources ONLY the code domain.

Trigger (2026-07-13): the frozen v2 code domain (BigCodeBench-Hard stdlib-only)
calibrated at 48% on LM Studio but measured 35% (21/60, mono N=5) on the
production Ollama stack — BELOW the [0.4, 0.7] band. Per the domain-aggregate
rule (Amendment 2026-07-09), the whole domain re-sources mechanically.

Mechanical rung between plain-BCB (89%, above band) and BCB-Hard (35%, below):
a deterministic 12-item mix — the first 6 validating stdlib-only items from
bigcodebench-hard plus the first 6 validating stdlib-only items from plain
bigcodebench whose task_id is NOT in the hard set (no duplicates). No outcome
peeking; selection depends only on dataset order + validation.

Math (AIME 2025) and multihop (MuSiQue open-book) carry over UNCHANGED with the
same task_ids. tasks/frontier_v2_manifest.json is immutable and stays intact.

Usage: python scripts/build_frontier_v2_1.py
"""
import ast
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from backends.base import Task
from harness.graders import grade

DS = "https://datasets-server.huggingface.co/rows"

STDLIB_OK = {
    "random", "itertools", "collections", "math", "re", "string", "functools",
    "operator", "datetime", "time", "json", "csv", "os", "heapq", "bisect",
    "statistics", "copy", "textwrap", "unicodedata", "hashlib", "base64",
    "sys", "glob", "shutil", "pathlib", "io", "struct", "binascii", "codecs",
    "html", "urllib", "queue", "threading", "pickle", "sqlite3", "zlib",
    "gzip", "tarfile", "zipfile", "secrets", "uuid", "calendar", "decimal",
    "fractions",
}

CHECK_WRAPPER = """

def check(candidate):
    import unittest
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCases)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    assert result.wasSuccessful(), f"{len(result.failures)} failures, {len(result.errors)} errors"
"""


def fetch(ds, cfg, split, offset, length=100, attempts=5):
    import time
    q = urllib.parse.urlencode({"dataset": ds, "config": cfg, "split": split,
                                "offset": offset, "length": length})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(f"{DS}?{q}", timeout=60) as r:
                return [x["row"] for x in json.load(r)["rows"]]
        except Exception as exc:  # 5xx / timeouts are transient on this endpoint
            if i == attempts - 1:
                raise
            wait = 2 ** (i + 1)
            print(f"  [fetch] {exc} — retry {i+1}/{attempts-1} in {wait}s")
            time.sleep(wait)


def stdlib_only(row):
    raw = row.get("libs") or "[]"
    libs = ast.literal_eval(raw) if isinstance(raw, str) else list(raw)
    return set(libs) <= STDLIB_OK, libs


def self_grades(row, test_src):
    reference = row["code_prompt"] + row["canonical_solution"]
    t = Task("v", "code", "", grading={"entry_point": row["entry_point"], "test": test_src})
    ok, _ = grade(t, f"```python\n{reference}\n```")
    return ok, reference


def build_from(dataset, exclude_ids, source_label, difficulty_note, target=6):
    out = []
    for off in range(0, 600, 100):
        for r in fetch(dataset, "default", "v0.1.4", off):
            if r["task_id"] in exclude_ids:
                continue
            ok_libs, libs = stdlib_only(r)
            if not ok_libs:
                continue
            test_src = r["test"] + CHECK_WRAPPER
            ok, reference = self_grades(r, test_src)
            if not ok:
                continue
            out.append({
                "domain": "code", "tier": "frontier",
                "source_id": f"{source_label}:{r['task_id']}",
                "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": (f"v2.1 code mix ({difficulty_note}; libs: "
                                     f"{', '.join(libs) or 'none'}). BCB-Hard-only domain measured 35% "
                                     "mono N=5 on the production Ollama stack (below band) 2026-07-13."),
                "prompt": ("Complete this Python function. Return only the full function "
                           "(with any needed imports) in a single ```python code block.\n\n"
                           + r["complete_prompt"].strip()),
                "answer": None, "reference_solution": reference,
                "grading": {"entry_point": r["entry_point"], "test": test_src},
                "_src_task_id": r["task_id"],
            })
            if len(out) >= target:
                return out
    return out


def build_via_network():
    hard_ids = set()
    for off in (0, 100):
        for r in fetch("bigcode/bigcodebench-hard", "default", "v0.1.4", off):
            hard_ids.add(r["task_id"])
    hard = build_from("bigcode/bigcodebench-hard", set(), "bigcodebench-hard-v0.1.4",
                      "hard rung", target=6)
    easy = build_from("bigcode/bigcodebench", hard_ids | {i["_src_task_id"] for i in hard},
                      "bigcodebench-v0.1.4", "plain rung", target=6)
    return hard, easy


def build_via_local_artifacts():
    """Outage fallback (2026-07-13, HF datasets-server 503): assemble the same
    mechanical selection from committed artifacts — both source sets were built
    by the identical first-N-validating rule from the same dataset ordering.
    Hard rung: first 6 code items of the frozen v2 manifest. Plain rung: first 6
    code items of the v2.0-era manifest (git 00b5b96) not in the known hard ids
    (overlap verified NONE against the 12 known; re-verify against the full
    148-item hard list when the endpoint recovers — recorded in the manifest)."""
    import subprocess
    frozen = json.load(open("tasks/frontier_v2_manifest.json"))
    hard = [dict(t) for t in frozen["tasks"] if t["domain"] == "code"][:6]
    old = json.loads(subprocess.check_output(
        ["git", "show", "00b5b96:tasks/frontier_v2_manifest.json"]))
    hard_src = {t["source_id"].split(":")[1] for t in frozen["tasks"] if t["domain"] == "code"}
    easy = [dict(t) for t in old["tasks"] if t["domain"] == "code"
            and t["source_id"].split(":")[1] not in hard_src][:6]
    for t in hard:
        t["id_status"] = "CANDIDATE_UNCALIBRATED"
        t["selection_reason"] = ("v2.1 code mix (hard rung; carried from frozen v2 first-6). "
                                 "Assembled from local artifacts during HF endpoint outage.")
    for t in easy:
        t["id_status"] = "CANDIDATE_UNCALIBRATED"
        t["selection_reason"] = ("v2.1 code mix (plain rung; v2.0-era first-6 excl. known hard ids). "
                                 "Assembled from local artifacts during HF endpoint outage; full "
                                 "hard-set exclusion re-verification pending endpoint recovery.")
    return hard, easy


try:
    hard_items, easy_items = build_via_network()
except Exception as exc:
    print(f"[build] network path failed ({exc}); using local-artifact fallback")
    hard_items, easy_items = build_via_local_artifacts()

code_items = hard_items + easy_items
for i, t in enumerate(code_items, 1):
    t["task_id"] = f"fx21-code-{i:03d}"
    t.pop("_src_task_id", None)

prev = json.load(open("tasks/frontier_v2_manifest.json"))
carried = [t for t in prev["tasks"] if t["domain"] in ("math", "multihop")]

manifest = {
    "_comment": ("FRONTIER TIER v2.1 — code domain re-sourced (2026-07-13). The frozen v2 code domain "
                 "(BigCodeBench-Hard stdlib-only) measured 35% mono N=5 on the production Ollama stack, "
                 "below the [0.4,0.7] band (LM Studio calibration had it at 48% — cross-stack drift). "
                 "v2.1 code = deterministic 6+6 mix of bigcodebench-hard and plain bigcodebench "
                 "(stdlib-only, first-N validating, hard ids excluded from the plain pull). Math and "
                 "multihop carried UNCHANGED with the same task_ids. CANDIDATE_UNCALIBRATED until the "
                 "code domain passes mono N=5 on the PRODUCTION stack (Ollama). v2 manifest remains "
                 "immutable; datasets collected against v2 are v2 data. See Amendment Log 2026-07-13."),
    "tier": "frontier", "frozen": False, "frozen_on": None,
    "calibration_status": "CODE_RECALIBRATION_PENDING",
    "tasks": carried[:12] + code_items + carried[12:],
}
# keep original domain order: math, code, multihop
math_items = [t for t in carried if t["domain"] == "math"]
hop_items = [t for t in carried if t["domain"] == "multihop"]
manifest["tasks"] = math_items + code_items + hop_items

with open("tasks/frontier_v2_1_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"wrote v2.1: math={len(math_items)} code={len(code_items)} "
      f"(hard={len(hard_items)}, plain={len(easy_items)}) multihop={len(hop_items)}")
