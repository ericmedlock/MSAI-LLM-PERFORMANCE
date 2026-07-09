"""Verify baseline manifest items against their claimed upstream benchmark sources.

Closes the `id_status: PLACEHOLDER_PENDING_FREEZE` provenance gap: every item that
claims a real upstream identity (GSM8K train index, HumanEval task id, HotpotQA dev
question) is fetched from the public source and compared — prompt text and answer.
Items whose source_id says "-style" are project-authored by design (their reference
answers are already exercised by tests/test_frontier_tasks.py-style self-grading);
they carry no upstream identity and are marked PROJECT_AUTHORED.

Usage:
    python scripts/verify_task_ids.py                 # report only
    python scripts/verify_task_ids.py --write         # also update id_status in the manifest

Downloads are cached under .cache/task_verify/ (gitignored). Network is required on
first run only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "tasks" / "manifest.json"
CACHE = REPO / ".cache" / "task_verify"

SOURCES = {
    "gsm8k_train": "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/train.jsonl",
    "humaneval": "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz",
}
# The canonical HotpotQA JSON host (curtis.ml.cmu.edu) is flaky, so query the
# HF datasets-server /filter endpoint (SQL WHERE on the mirrored dataset) instead.
HOTPOT_FILTER = (
    "https://datasets-server.huggingface.co/filter"
    "?dataset=hotpotqa%2Fhotpot_qa&config=distractor&split={split}&where={where}"
)

VERIFIED = "VERIFIED_UPSTREAM_EXACT"
ADAPTED = "VERIFIED_UPSTREAM_ADAPTED"
AUTHORED = "PROJECT_AUTHORED"


def fetch(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    url = SOURCES[name]
    dest = CACHE / url.rsplit("/", 1)[-1]
    if not dest.exists():
        print(f"  downloading {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "task-id-verify"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())
    return dest


def norm(text: str) -> str:
    """Whitespace-insensitive comparison form."""
    return re.sub(r"\s+", " ", text).strip()


def gsm8k_final_answer(answer_field: str) -> str:
    return answer_field.rsplit("####", 1)[-1].strip().replace(",", "")


def verify_gsm8k(item: dict) -> tuple[str | None, str]:
    m = re.search(r"train\[(\d+)\]", item["source_id"])
    if not m:
        return None, f"unrecognized gsm8k source_id: {item['source_id']!r}"
    idx = int(m.group(1))
    rows = [json.loads(line) for line in fetch("gsm8k_train").read_text().splitlines()]
    if idx >= len(rows):
        return None, f"train[{idx}] out of range ({len(rows)} rows)"
    row = rows[idx]
    if norm(row["question"]) != norm(item["prompt"]):
        return None, f"prompt differs from gsm8k train[{idx}]"
    upstream_ans = gsm8k_final_answer(row["answer"])
    if upstream_ans != str(item["answer"]).strip():
        return None, f"answer differs: upstream {upstream_ans!r} vs manifest {item['answer']!r}"
    return VERIFIED, f"gsm8k/main train[{idx}]: prompt + answer exact"


def verify_humaneval(item: dict) -> tuple[str | None, str]:
    m = re.search(r"(HumanEval/\d+)", item["source_id"])
    if not m:
        return None, f"unrecognized humaneval source_id: {item['source_id']!r}"
    want = m.group(1)
    with gzip.open(fetch("humaneval"), "rt") as f:
        rows = {r["task_id"]: r for r in map(json.loads, f)}
    row = rows.get(want)
    if row is None:
        return None, f"{want} not in upstream set"
    if row["entry_point"] != item["grading"].get("entry_point"):
        return None, (
            f"entry_point differs: upstream {row['entry_point']!r} "
            f"vs manifest {item['grading'].get('entry_point')!r}"
        )
    if norm(row["prompt"]) in norm(item["prompt"]):
        return VERIFIED, f"{want}: canonical prompt embedded verbatim, entry_point exact"
    # Freeze forbids editing prompts post-hoc, so verify the function identity
    # (signature + every doctest) and record the docstring paraphrase honestly.
    sig = next(line for line in row["prompt"].splitlines() if line.startswith(f"def {row['entry_point']}"))
    doctests = [norm(line) for line in row["prompt"].splitlines() if line.strip().startswith(">>>")]
    manifest_norm = norm(item["prompt"])
    # Accept an added return annotation: match "def name(params)" ignoring what
    # follows the closing paren on either side.
    sig_stem = norm(sig.split(")")[0] + ")")
    if sig_stem not in manifest_norm:
        return None, f"{want} signature not found in manifest prompt"
    missing = [d for d in doctests if d not in manifest_norm]
    if missing:
        return None, f"{want} doctest(s) missing from manifest prompt: {missing}"
    return ADAPTED, (
        f"{want}: signature, all {len(doctests)} doctests, and entry_point exact; "
        "docstring wording lightly paraphrased at transcription"
    )


def loose(text: str) -> str:
    """Punctuation- and case-insensitive comparison form."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _hotpot_filter(where: str, split: str, cache_key: str) -> list[dict]:
    import hashlib

    digest = hashlib.sha256(where.encode()).hexdigest()[:8]
    dest = CACHE / f"{cache_key}.{digest}.json"
    if not dest.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = HOTPOT_FILTER.format(split=split, where=urllib.parse.quote(where, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "task-id-verify"})
        with urllib.request.urlopen(req, timeout=90) as r:
            dest.write_bytes(r.read())
    return [r["row"] for r in json.loads(dest.read_text()).get("rows", [])]


def verify_hotpotqa(item: dict) -> tuple[str | None, str]:
    """Locate the exact question via HF datasets-server SQL filter (cached).

    The endpoint 500s on some quoted apostrophes, so the fallback LIKE query uses
    the longest apostrophe-free fragment and matches punctuation-insensitively
    client-side (transcription may differ by a comma).
    """
    q = item["prompt"]
    tid = re.sub(r"\W+", "_", item["task_id"])
    # Longest punctuation-free run: immune to commas/apostrophes that may have
    # been added or dropped during transcription.
    fragment = max(re.split(r"[^A-Za-z0-9 ]+", q), key=len).strip()
    for split in ("validation", "train"):
        rows: list[dict] = []
        try:
            esc = q.replace("'", "''")
            rows = _hotpot_filter(f"\"question\"='{esc}'", split, f"{tid}_{split}_exact")
        except Exception:
            pass  # endpoint rejects some escaped strings; the LIKE fallback covers it
        if not rows:
            try:
                rows = _hotpot_filter(
                    f"\"question\" LIKE '%{fragment}%'", split, f"{tid}_{split}_like"
                )
            except Exception as exc:
                return None, f"hotpotqa filter query failed on {split}: {exc}"
        for row in rows:
            if loose(row["question"]) != loose(q):
                continue
            if loose(row["answer"]) != loose(str(item["answer"])):
                return None, (
                    f"answer differs: upstream {row['answer']!r} vs manifest {item['answer']!r}"
                )
            exact = norm(row["question"]) == norm(q)
            status = VERIFIED if exact else ADAPTED
            note = "question + answer exact" if exact else (
                "answer exact; question punctuation differs slightly from upstream"
            )
            return status, f"hotpotqa distractor/{split} id={row['id']}: {note}"
    return None, "question not found in hotpotqa distractor validation or train"


VERIFIERS = {"gsm8k": verify_gsm8k, "humaneval": verify_humaneval, "hotpotqa": verify_hotpotqa}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="update id_status in the manifest")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    failures = 0
    for item in manifest["tasks"]:
        tid = item["task_id"]
        if "-style" in item["source_id"]:
            status, detail = AUTHORED, "project-authored item; no upstream identity by design"
        else:
            status, detail = VERIFIERS[item["domain"]](item)
            if status is None:
                status = "MISMATCH"
                failures += 1
        print(f"{tid:16s} {status:24s} {detail}")
        if args.write and status != "MISMATCH":
            item["id_status"] = status

    if failures:
        print(f"\n{failures} item(s) FAILED verification — manifest NOT updated for those items.")
    if args.write:
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwrote {MANIFEST.relative_to(REPO)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
