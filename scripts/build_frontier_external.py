"""Fetch harder, externally-calibrated tasks (MATH-500 / MBPP / MuSiQue) via the
HuggingFace public datasets-server, convert to the frontier manifest schema, and
VALIDATE each by running the real harness grader. Only self-consistent items are
kept. Writes tasks/frontier_external_manifest.json.
"""
import json, re, sys, urllib.request, urllib.parse
sys.path.insert(0, ".")
from backends.base import Task
from harness.graders import grade

DS = "https://datasets-server.huggingface.co/rows"

def fetch(ds, cfg, split, offset, length=100):
    q = urllib.parse.urlencode({"dataset": ds, "config": cfg, "split": split,
                                "offset": offset, "length": length})
    with urllib.request.urlopen(f"{DS}?{q}", timeout=30) as r:
        return [x["row"] for x in json.load(r)["rows"]]

def validate_answer(domain, prompt, answer):
    t = Task("v", domain, prompt, answer=answer)
    ok, _ = grade(t, answer)
    return ok

def validate_code(prompt, entry_point, test_src, reference):
    t = Task("v", "code", prompt, grading={"entry_point": entry_point, "test": test_src})
    ok, err = grade(t, f"```python\n{reference}\n```")
    return ok, err

# ---------------- MATH-500: keep plain-integer answers, prefer level >=3 ------- #
def build_math(target=8):
    out = []
    for off in range(0, 500, 100):
        for r in fetch("HuggingFaceH4/MATH-500", "default", "test", off):
            ans = str(r["answer"]).strip()
            if not re.fullmatch(r"-?\d+", ans):        # integer answers only (grader compares last number)
                continue
            if int(r.get("level", 0)) < 3:              # "harder": competition levels 3-5
                continue
            prompt = (r["problem"].strip() +
                      "\n\nGive the final answer as a single integer on the last line.")
            if not validate_answer("math", prompt, ans):
                continue
            out.append({
                "task_id": f"fx-math-{len(out)+1:03d}", "domain": "math", "tier": "frontier",
                "source_id": f"MATH-500:{r['unique_id']}", "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": f"MATH competition L{r['level']} ({r['subject']}); integer answer, "
                                    f"harder than baseline gsm8k.",
                "prompt": prompt, "answer": ans, "grading": {},
            })
            if len(out) >= target:
                return out
    return out

# ---------------- MBPP sanitized: asserts -> check(), validate by running ------ #
def build_code(target=8):
    out = []
    for off in range(0, 250, 100):
        for r in fetch("google-research-datasets/mbpp", "sanitized", "test", off):
            code = r["code"]; tests = r["test_list"]; imports = r.get("test_imports") or []
            defs = re.findall(r"def\s+(\w+)\s*\(", code)
            if not defs:
                continue
            joined = " ".join(tests)
            entry = next((d for d in defs if re.search(rf"\b{re.escape(d)}\s*\(", joined)), defs[0])
            body = "\n".join(imports) + ("\n\n" if imports else "")
            body += "def check(candidate):\n" + "".join(f"    {t}\n" for t in tests)
            ok, err = validate_code("", entry, body, code)
            if not ok:                                  # drop anything that doesn't self-verify
                continue
            desc = r["prompt"].strip().rstrip(".")
            prompt = (f"{desc}. Implement it as a Python function named `{entry}`. "
                      f"Return only the full function in a single ```python code block.")
            out.append({
                "task_id": f"fx-code-{len(out)+1:03d}", "domain": "code", "tier": "frontier",
                "source_id": f"mbpp-sanitized:{r['task_id']}", "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": "MBPP programming problem (unit-test graded); DP/logic beyond baseline humaneval subset.",
                "prompt": prompt, "answer": None, "reference_solution": code,
                "grading": {"entry_point": entry, "test": body},
            })
            if len(out) >= target:
                return out
    return out

# ---------------- MuSiQue: 2-4 hop, short string answers ----------------------- #
def build_multihop(target=6):
    out = []
    for off in range(0, 400, 100):
        for r in fetch("dgslibisey/MuSiQue", "default", "validation", off):
            if not r.get("answerable", False):
                continue
            ans = str(r["answer"]).strip()
            if not (0 < len(ans.split()) <= 5) or not ans.isascii():
                continue
            hops = len(r.get("question_decomposition") or [])
            prompt = r["question"].strip() + "\n\nGive only the answer on the last line."
            if not validate_answer("multihop", prompt, ans):
                continue
            out.append({
                "task_id": f"fx-hop-{len(out)+1:03d}", "domain": "multihop", "tier": "frontier",
                "source_id": f"musique:{r['id']}", "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": f"MuSiQue {hops}-hop question; more hops than baseline hotpotqa.",
                "prompt": prompt, "answer": ans, "grading": {},
            })
            if len(out) >= target:
                return out
    return out

math, code, hop = build_math(), build_code(), build_multihop()
tasks = math + code + hop
manifest = {
    "_comment": ("FRONTIER TIER — EXTERNALLY SOURCED (harder candidates, 2026-07-08). Items pulled from "
                 "public calibrated benchmarks and converted to the objective graders: math=MATH-500 "
                 "(integer-answer, level>=3), code=MBPP sanitized (unit-test graded), multihop=MuSiQue "
                 "(2-4 hop). Every code item's reference_solution was run through the real grader; every "
                 "math/multihop gold answer self-grades. Still CANDIDATE_UNCALIBRATED: calibrate against "
                 "the serving model (KEEP monolithic single-pass acc in ~0.4-0.7) before freezing. SWE-bench "
                 "and GAIA were evaluated and rejected: they need repo+Docker execution / live web tools that "
                 "this single-prompt, in-process grader cannot run. See docs/TASK_TIERS.md."),
    "tier": "frontier", "frozen": False, "frozen_on": None,
    "calibration_status": "CANDIDATE_UNCALIBRATED",
    "tasks": tasks,
}
with open("tasks/frontier_external_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"wrote {len(tasks)} items: math={len(math)} code={len(code)} multihop={len(hop)}")
