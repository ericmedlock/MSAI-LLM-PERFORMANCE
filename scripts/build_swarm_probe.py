"""Build tasks/swarm_probe_manifest.json — the exploratory 4th suite.

Purpose (vault: "Swarm Probe Suite — Design", 2026-07-13): tasks with DISCRETE
answer spaces where majority voting can act — the probe arm for "where can the
swarm actually shine?", motivated by the temp-0 vote-degeneracy finding (E12).
NOT part of the pre-registered confirmatory tiers; tier is "probe".

Composition (mechanical, first-N validating, no outcome peeking):
- 6 x MMLU-Pro (10-option multiple choice; open dataset; answer = letter)
- 6 x DROP (short discrete numeric/span answers over a passage)

Both grade via the normalized-string 'probe' domain (graders.py). Calibrate
mono N=5 on the production stack (same band rule) before any swarm variant run.

Usage: python scripts/build_swarm_probe.py   (needs the HF datasets-server up)
"""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from backends.base import Task
from harness.graders import grade

DS = "https://datasets-server.huggingface.co/rows"


def fetch(ds, cfg, split, offset, length=100, attempts=5):
    q = urllib.parse.urlencode({"dataset": ds, "config": cfg, "split": split,
                                "offset": offset, "length": length})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(f"{DS}?{q}", timeout=60) as r:
                return [x["row"] for x in json.load(r)["rows"]]
        except Exception as exc:
            if i == attempts - 1:
                raise
            wait = 2 ** (i + 1)
            print(f"  [fetch] {exc} — retry in {wait}s")
            time.sleep(wait)


def validate(prompt, answer):
    ok, _ = grade(Task("v", "probe", prompt, answer=answer), answer)
    return ok


LETTERS = "ABCDEFGHIJ"


def build_mc(target=6):
    out = []
    for off in range(0, 400, 100):
        for r in fetch("TIGER-Lab/MMLU-Pro", "default", "test", off):
            options = r.get("options") or []
            idx = r.get("answer_index")
            if not options or idx is None or not (0 <= idx < len(options)) or len(options) < 6:
                continue
            gold = LETTERS[idx]
            opts = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
            prompt = (f"{r['question'].strip()}\n\n{opts}\n\n"
                      "Answer with the letter of the correct option only, on the last line.")
            if not validate(prompt, gold):
                continue
            out.append({
                "task_id": f"probe-mc-{len(out)+1:03d}", "domain": "probe", "tier": "probe",
                "source_id": f"mmlu-pro:{r.get('question_id', off)}",
                "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": (f"MMLU-Pro {r.get('category','?')} — 10-way discrete vote space "
                                     "for the swarm probe (E12: voting needs a small answer space)."),
                "prompt": prompt, "answer": gold, "grading": {},
            })
            if len(out) >= target:
                return out
    return out


def build_drop(target=6):
    out = []
    for off in range(0, 400, 100):
        for r in fetch("ucinlp/drop", "default", "validation", off):
            spans = (r.get("answers_spans") or {}).get("spans") or []
            if len(spans) != 1:
                continue
            ans = str(spans[0]).strip()
            if not ans or len(ans.split()) > 4 or not ans.isascii():
                continue
            prompt = (f"Answer the question using ONLY the passage below.\n\n"
                      f"{r['passage'].strip()}\n\nQuestion: {r['question'].strip()}\n\n"
                      "Give only the answer on the last line.")
            if len(prompt) > 6000:
                continue
            if not validate(prompt, ans):
                continue
            out.append({
                "task_id": f"probe-drop-{len(out)+1:03d}", "domain": "probe", "tier": "probe",
                "source_id": f"drop:{r.get('query_id','?')}",
                "id_status": "CANDIDATE_UNCALIBRATED",
                "selection_reason": ("DROP discrete extraction — short answer keys where peer "
                                     "error diversity is plausible (swarm probe)."),
                "prompt": prompt, "answer": ans, "grading": {},
            })
            if len(out) >= target:
                return out
    return out


mc, drop = build_mc(), build_drop()
manifest = {
    "_comment": ("SWARM PROBE SUITE (exploratory 4th suite, 2026-07-13). Discrete answer spaces "
                 "where majority voting can act. NOT pre-registered/confirmatory; runs after the "
                 "v2.1 N=5. Calibrate mono N=5 on the production stack before swarm variants "
                 "(SWARM_PEER_TEMP / SWARM_VOTE). See vault 'Swarm Probe Suite — Design'."),
    "tier": "probe", "frozen": False, "frozen_on": None,
    "calibration_status": "CANDIDATE_UNCALIBRATED",
    "tasks": mc + drop,
}
with open("tasks/swarm_probe_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"wrote {len(mc)+len(drop)} probe candidates: mc={len(mc)} drop={len(drop)}")
