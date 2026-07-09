"""Build the frontier-v2 candidate manifest, fixing the two calibration failures
observed on the v1 external set (2026-07-09, full-size system test):

- code (MBPP sanitized) SATURATED: 120/120 correct at 32B -> replaced with
  BigCodeBench (stdlib-only subset), which is harder by construction
  (multi-step library composition, rigorous unittest suites).
- multihop (MuSiQue closed-book) FLOORED: 0% at 32B -> MuSiQue is calibrated as a
  reading-comprehension benchmark, so v2 provides the supporting paragraphs in
  the prompt (plus distractors up to a context budget). The bottleneck becomes
  multi-step reasoning over given text instead of parametric recall.
- math (MATH-500 L>=3) was IN BAND (65% at 32B) -> carried over unchanged,
  same task_ids, still subject to the 14B calibration pass.

Every item self-grades through the real harness grader before inclusion.
Candidates stay CANDIDATE_UNCALIBRATED until the monolithic N=5 pre-pass against
the pinned model keeps only items with single-pass accuracy in ~[0.4, 0.7]
(pre-registered criterion; items outside the band are dropped, not tuned).

Usage: python scripts/build_frontier_v2.py   (writes tasks/frontier_v2_manifest.json)
"""
import ast
import json
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from backends.base import Task
from harness.graders import grade

DS = "https://datasets-server.huggingface.co/rows"

# Prompt must fit num_ctx (8192) minus max_tokens (6144) minus margin.
CONTEXT_CHAR_BUDGET = 5000

STDLIB_OK = {
    "random", "itertools", "collections", "math", "re", "string", "functools",
    "operator", "datetime", "time", "json", "csv", "os", "heapq", "bisect",
    "statistics", "copy", "textwrap", "unicodedata", "hashlib", "base64",
}


def fetch(ds, cfg, split, offset, length=100):
    q = urllib.parse.urlencode({"dataset": ds, "config": cfg, "split": split,
                                "offset": offset, "length": length})
    with urllib.request.urlopen(f"{DS}?{q}", timeout=60) as r:
        return [x["row"] for x in json.load(r)["rows"]]


def validate_answer(domain, prompt, answer):
    t = Task("v", domain, prompt, answer=answer)
    ok, _ = grade(t, answer)
    return ok


def validate_code(entry_point, test_src, reference):
    t = Task("v", "code", "", grading={"entry_point": entry_point, "test": test_src})
    ok, err = grade(t, f"```python\n{reference}\n```")
    return ok, err


CHECK_WRAPPER = """

def check(candidate):
    import unittest
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCases)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    assert result.wasSuccessful(), f"{len(result.failures)} failures, {len(result.errors)} errors"
"""


# ------- code: BigCodeBench v0.1.4, stdlib-only, unittest suites --------------- #
def build_code(target=16):
    out = []
    for off in range(0, 600, 100):
        for r in fetch("bigcode/bigcodebench", "default", "v0.1.4", off):
            raw_libs = r.get("libs") or "[]"
            libs = ast.literal_eval(raw_libs) if isinstance(raw_libs, str) else list(raw_libs)
            if not set(libs) <= STDLIB_OK:
                continue
            test_src = r["test"] + CHECK_WRAPPER
            reference = r["code_prompt"] + r["canonical_solution"]
            ok, err = validate_code(r["entry_point"], test_src, reference)
            if not ok:  # drop anything that doesn't self-verify (incl. flaky tests)
                continue
            prompt = ("Complete this Python function. Return only the full function "
                      "(with any needed imports) in a single ```python code block.\n\n"
                      + r["complete_prompt"].strip())
            out.append({
                "task_id": f"fx2-code-{len(out)+1:03d}", "domain": "code", "tier": "frontier",
                "source_id": f"bigcodebench-v0.1.4:{r['task_id']}",
                "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": (f"BigCodeBench item (libs: {', '.join(libs) or 'none'}); "
                                     "harder than MBPP, which saturated (120/120) at 32B on 2026-07-09."),
                "prompt": prompt, "answer": None,
                "reference_solution": reference,
                "grading": {"entry_point": r["entry_point"], "test": test_src},
            })
            if len(out) >= target:
                return out
    return out


# ------- multihop: MuSiQue WITH supporting context + distractors ---------------- #
def build_multihop(target=12):
    out = []
    for off in range(0, 800, 100):
        for r in fetch("dgslibisey/MuSiQue", "default", "validation", off):
            if not r.get("answerable", False):
                continue
            ans = str(r["answer"]).strip()
            if not (0 < len(ans.split()) <= 5) or not ans.isascii():
                continue
            paras = r["paragraphs"]
            support = [p for p in paras if p["is_supporting"]]
            distract = [p for p in paras if not p["is_supporting"]]
            blocks = [f"[{p['title']}]\n{p['paragraph_text']}" for p in support]
            if sum(len(b) for b in blocks) > CONTEXT_CHAR_BUDGET:
                continue  # supporting evidence alone must fit the budget
            for p in distract:  # pad with distractors while budget allows
                b = f"[{p['title']}]\n{p['paragraph_text']}"
                if sum(len(x) for x in blocks) + len(b) > CONTEXT_CHAR_BUDGET:
                    break
                blocks.append(b)
            hops = len(r.get("question_decomposition") or [])
            prompt = ("Answer the question using ONLY the context passages below.\n\n"
                      + "\n\n".join(blocks)
                      + f"\n\nQuestion: {r['question'].strip()}"
                      + "\n\nGive only the answer on the last line.")
            if not validate_answer("multihop", prompt, ans):
                continue
            out.append({
                "task_id": f"fx2-hop-{len(out)+1:03d}", "domain": "multihop", "tier": "frontier",
                "source_id": f"musique:{r['id']} (with context)",
                "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": (f"MuSiQue {hops}-hop WITH supporting passages "
                                     f"(+{len(blocks)-len(support)} distractors); closed-book variant "
                                     "floored at 0% (32B, 2026-07-09) because the bottleneck was recall, "
                                     "not reasoning."),
                "prompt": prompt, "answer": ans, "grading": {},
            })
            if len(out) >= target:
                return out
    return out


# ------- math: carry over the in-band MATH-500 items unchanged ------------------ #
def carry_math():
    prev = json.load(open("tasks/frontier_external_manifest.json"))
    items = [t for t in prev["tasks"] if t["domain"] == "math"]
    for t in items:
        t["selection_reason"] += " Carried into v2 unchanged: in band (65%) at 32B on 2026-07-09."
    return items


math_items, code_items, hop_items = carry_math(), build_code(), build_multihop()
tasks = math_items + code_items + hop_items
manifest = {
    "_comment": ("FRONTIER TIER v2 — recalibrated candidates (2026-07-09). Fixes from the v1 external "
                 "set's full-size system test: code source MBPP->BigCodeBench (stdlib-only; MBPP "
                 "saturated 100% at 32B), multihop MuSiQue closed-book -> WITH supporting passages "
                 "(closed-book floored at 0%; upstream calibration assumes provided context), math "
                 "carried over (in band). All items self-grade through the real grader. "
                 "CANDIDATE_UNCALIBRATED until the monolithic N=5 pre-pass on the PINNED model keeps "
                 "items with single-pass accuracy in ~[0.4,0.7]; out-of-band items are dropped, not "
                 "tuned (pre-registered criterion). See PRE_REGISTRATION.md Amendment Log + docs/TASK_TIERS.md."),
    "tier": "frontier", "frozen": False, "frozen_on": None,
    "calibration_status": "CANDIDATE_UNCALIBRATED",
    "tasks": tasks,
}
with open("tasks/frontier_v2_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"wrote {len(tasks)} candidates: math={len(math_items)} code={len(code_items)} multihop={len(hop_items)}")
