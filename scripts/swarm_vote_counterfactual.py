"""Swarm vote-mechanism counterfactual re-vote (follow-up to swarm 2.0 cell).

SECONDARY post-processing analysis over saved swarm traces. The primary
metric is untouched: this script never rewrites result rows. It replays each
swarm row's peer answers through the backend's own election rule under
alternative vote-key functions and asks what the row would have scored.

Pre-declared mechanical rules (do not change without a new amendment):
  * Election is byte-identical to ``SwarmBackend._majority_vote``: peers with
    an empty vote key ABSTAIN; plurality wins; tie-break = earliest valid
    peer in a winning group; all-abstain = earliest peer, flagged.
  * V0 (fidelity check): pinned exact keys — must reproduce the recorded
    outcome; any mismatch is reported and voids the replay for that row.
  * V1 (ast): ``vote_key_ast`` — AST-normalized code keys, other domains
    unchanged. This is exactly the shipped ``SWARM_VOTE=ast`` behavior.
  * V2 (abstain-refusal): multihop keys matching the refusal pattern below
    abstain instead of voting. Other domains unchanged.
  * V3: V1 + V2 combined.
  * Refusal pattern (fixed): a normalized multihop key containing one of
    "not mentioned", "not provided", "not stated", "not specified",
    "not found", "not available", "cannot determine", "cannot be determined",
    "no answer", "unknown" ABSTAINS.

Usage:
  .venv/bin/python scripts/swarm_vote_counterfactual.py \
      results/frontier-v2.1-local-swarm20-14b-n5.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.graders import grade, vote_key, vote_key_ast
from harness.task_loader import load_tasks

MANIFESTS = (
    "tasks/frontier_v2_manifest.json",
    "tasks/frontier_v2_1_manifest.json",
)

_REFUSAL = re.compile(
    r"(not (mentioned|provided|stated|specified|found|available)"
    r"|cannot (be )?determin|no answer|unknown)"
)


def key_v0(domain: str, answer: str) -> str:
    return vote_key(domain, answer)


def key_v1(domain: str, answer: str) -> str:
    return vote_key_ast(domain, answer)


def key_v2(domain: str, answer: str) -> str:
    k = vote_key(domain, answer)
    if domain in ("hotpotqa", "multihop") and _REFUSAL.search(k):
        return ""  # abstain
    return k


def key_v3(domain: str, answer: str) -> str:
    k = vote_key_ast(domain, answer)
    if domain in ("hotpotqa", "multihop") and _REFUSAL.search(k):
        return ""
    return k


VARIANTS = (("v0-exact", key_v0), ("v1-ast", key_v1),
            ("v2-abstain", key_v2), ("v3-both", key_v3))


def elect(domain: str, peers: list[dict], keyfn) -> tuple[dict, bool, bool]:
    """Mirror SwarmBackend._majority_vote. Returns (chosen, tie, all_abstained)."""
    ordered = sorted(peers, key=lambda p: p["index"])
    keys = [keyfn(domain, p["answer"]) for p in ordered]
    valid = [(p, k) for p, k in zip(ordered, keys) if k != ""]
    if not valid:
        return ordered[0], False, True
    counts: dict[str, int] = {}
    for _, k in valid:
        counts[k] = counts.get(k, 0) + 1
    top = max(counts.values())
    winners = {k for k, c in counts.items() if c == top}
    chosen = next(p for p, k in valid if k in winners)
    return chosen, len(winners) > 1, False


def main(paths: list[str]) -> None:
    tasks = {}
    for m in MANIFESTS:
        if Path(m).exists():
            tasks.update({t.task_id: t for t in load_tasks(m)})

    for path in paths:
        rows = [json.loads(l) for l in open(path) if l.strip()]
        rows = [r for r in rows if r.get("backend") == "swarm"]
        if not rows:
            print(f"{path}: no swarm rows, skipped")
            continue
        print(f"\n=== {path} ({len(rows)} swarm rows) ===")

        fidelity_bad = 0
        acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # variant -> domain -> [hit, n]
        ties = defaultdict(int)
        flips = defaultdict(list)

        for r in rows:
            task = tasks.get(r["task_id"])
            if task is None:
                continue
            peers = json.loads(r["raw_trace"]) if isinstance(r["raw_trace"], str) else r["raw_trace"]
            dom = task.domain

            chosen0, _, _ = elect(dom, peers, key_v0)
            ok0, _ = grade(task, chosen0["answer"])
            if bool(ok0) != bool(r["correct"]):
                fidelity_bad += 1
                continue  # replay does not reproduce the pinned row; exclude

            for name, keyfn in VARIANTS:
                chosen, tie, _ = elect(dom, peers, keyfn)
                ok, _ = grade(task, chosen["answer"])
                acc[name][dom][0] += bool(ok)
                acc[name][dom][1] += 1
                ties[name] += tie
                if name != "v0-exact" and bool(ok) != bool(ok0):
                    flips[name].append(
                        (r["task_id"], "wrong->RIGHT" if ok else "RIGHT->wrong")
                    )

        n_ok = sum(d[1] for d in acc["v0-exact"].values())
        print(f"fidelity: {n_ok}/{len(rows)} rows reproduce pinned outcome "
              f"({fidelity_bad} excluded)")
        print(f"{'variant':12s} {'overall':>8s} " +
              " ".join(f"{d:>9s}" for d in ("math", "code", "multihop")) +
              f" {'ties':>5s}")
        for name, _ in VARIANTS:
            doms = acc[name]
            tot_h = sum(h for h, _ in doms.values())
            tot_n = sum(n for _, n in doms.values())
            cells = []
            for d in ("math", "code", "multihop"):
                h, n = doms.get(d, (0, 0))
                cells.append(f"{h}/{n}" if n else "-")
            print(f"{name:12s} {tot_h/tot_n:8.1%} " +
                  " ".join(f"{c:>9s}" for c in cells) + f" {ties[name]:5d}")
        for name in ("v1-ast", "v2-abstain", "v3-both"):
            if flips[name]:
                summary = defaultdict(int)
                for tid, kind in flips[name]:
                    summary[(tid, kind)] += 1
                print(f"  {name} flips: " + ", ".join(
                    f"{tid} {kind} x{c}" for (tid, kind), c in sorted(summary.items())))


if __name__ == "__main__":
    main(sys.argv[1:] or ["results/frontier-v2.1-local-swarm20-14b-n5.jsonl"])
