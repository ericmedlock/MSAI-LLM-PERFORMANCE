"""Best-of-3 verifier-SELECTION counterfactual over saved swarm traces.

SECONDARY post-processing analysis (agentic_counterfactual.py pattern): never
rewrites result rows. Motivated by the 2026-07-17 oracle analysis: on the M5
epoch-2 swarm cell a perfect selector scores 63.9% vs 55.6% as-voted (+8.3
pts), and 19/180 rows have exactly ONE correct peer — a minority a vote can
never elect but a selector can.

Pre-declared mechanical rule (do not change without a new amendment):
  * For each swarm row, judge each of the 3 saved peer answers independently
    with the pinned agentic verifier prompt and the pinned decoding config.
  * Verdict = lenient parse: last standalone APPROVE/REVISE token decides;
    neither present -> REVISE (Amendment 2026-07-14 rule, byte-identical).
  * Selection = the APPROVED peer with the lowest index; if no peer is
    approved, fall back to the row's recorded as-voted answer.
  * Verifier call seed = row_trial_seed + 100 + peer_index (reproducible,
    collision-free: trial stride is 1000, peer offsets use +0..2).
  * Score the selected answer with the pinned grader.

Resumable: every verifier judgment is appended to the sidecar JSONL keyed by
(task_id, trial_seed, peer_index); rerunning skips existing judgments and
recomputes the summary from the sidecar.

Usage:
  .venv/bin/python scripts/swarm_select_counterfactual.py            # full run
  .venv/bin/python scripts/swarm_select_counterfactual.py --limit 2  # smoke
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backends.factory import build_client
from harness.config import load_config, load_dotenv
from harness.graders import grade
from harness.prompts import load_prompts
from harness.task_loader import load_tasks

_TOKEN = re.compile(r"\b(APPROVE|REVISE)\b")


def lenient_verdict(text: str) -> bool:
    hits = _TOKEN.findall(text.upper())
    return bool(hits) and hits[-1] == "APPROVE"


def trial_seed_of(row: dict) -> int:
    ts = row.get("trial_seed") or (row.get("metadata") or {}).get("trial_seed")
    if ts is None:
        raise SystemExit(f"row {row['task_id']} has no trial_seed — wrong epoch file?")
    return int(ts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="results/frontier-v2.1-local-14b.jsonl")
    ap.add_argument("--sidecar", default="results/counterfactuals/swarm-select-m5-epoch2.jsonl")
    ap.add_argument("--environment", default="local")
    ap.add_argument("--limit", type=int, default=0, help="rows to process (0 = all)")
    args = ap.parse_args()

    load_dotenv()
    config = load_config("config/config.yaml")
    prompts = load_prompts(config.prompts_dir)
    client = build_client(config, args.environment)
    tasks = {t.task_id: t for t in load_tasks("tasks/frontier_v2_1_manifest.json")}

    rows = [json.loads(l) for l in open(args.input) if l.strip()]
    rows = [r for r in rows if r.get("backend") == "swarm"]
    if args.limit:
        rows = rows[: args.limit]

    sidecar = Path(args.sidecar)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    done: dict[tuple, dict] = {}
    if sidecar.exists():
        for l in open(sidecar):
            j = json.loads(l)
            done[(j["task_id"], j["trial_seed"], j["peer_index"])] = j

    # phase 1: judge every peer (resumable)
    todo = 0
    with open(sidecar, "a") as out:
        for r in rows:
            ts = trial_seed_of(r)
            peers = json.loads(r["raw_trace"]) if isinstance(r["raw_trace"], str) else r["raw_trace"]
            for p in sorted(peers, key=lambda p: int(p["index"])):
                i = int(p["index"])
                if (r["task_id"], ts, i) in done:
                    continue
                task = tasks[r["task_id"]]
                user = f"Task:\n{task.prompt}\n\nCandidate answer:\n{p['answer']}"
                resp = client.chat(prompts.verifier_system, user, seed=ts + 100 + i)
                rec = {
                    "task_id": r["task_id"],
                    "trial_seed": ts,
                    "peer_index": i,
                    "approved": lenient_verdict(resp.text),
                    "verifier_seed": ts + 100 + i,
                    "verifier_tokens_out": resp.tokens_out,
                }
                out.write(json.dumps(rec) + "\n")
                out.flush()
                done[(r["task_id"], ts, i)] = rec
                todo += 1
                if todo % 25 == 0:
                    print(f"[select-cf] {todo} judgments this session "
                          f"({len(done)} total)", flush=True)

    # phase 2: selection + scoring from the sidecar
    sel_correct = voted_correct = fell_back = 0
    n = 0
    flips = defaultdict(int)
    for r in rows:
        ts = trial_seed_of(r)
        peers = sorted(
            (json.loads(r["raw_trace"]) if isinstance(r["raw_trace"], str) else r["raw_trace"]),
            key=lambda p: int(p["index"]),
        )
        judgments = [done.get((r["task_id"], ts, int(p["index"]))) for p in peers]
        if any(j is None for j in judgments):
            continue  # incomplete (only in --limit smoke runs)
        n += 1
        chosen = next((p for p, j in zip(peers, judgments) if j["approved"]), None)
        if chosen is None:
            fell_back += 1
            ok = bool(r["correct"])  # fall back to the as-voted outcome
        else:
            ok, _ = grade(tasks[r["task_id"]], chosen["answer"])
        sel_correct += bool(ok)
        voted_correct += bool(r["correct"])
        if ok and not r["correct"]:
            flips["wrong->RIGHT"] += 1
        elif r["correct"] and not ok:
            flips["RIGHT->wrong"] += 1

    print(f"\n=== best-of-3 verifier-selection counterfactual ({args.input}) ===")
    print(f"rows scored: {n} | judgments cached: {len(done)}")
    if n:
        print(f"as-voted:  {voted_correct}/{n} = {voted_correct/n:.1%}")
        print(f"selected:  {sel_correct}/{n} = {sel_correct/n:.1%}")
        print(f"flips: {dict(flips)} | no-peer-approved fallbacks: {fell_back}")
        print("reference: oracle best-of-3 = 63.9%, agentic epoch-2 = 57.8%, mono = 50.0%")


if __name__ == "__main__":
    main()
