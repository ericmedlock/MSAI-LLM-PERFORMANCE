# Task tiers: baseline vs frontier

## The problem this solves

Whether an agentic or swarm architecture beats a monolithic one is **decided by
the tasks you pick**, not just the architecture. The v1 pilot made this concrete:

- On the baseline suite, the pinned model (`deepseek-r1-distill-qwen-14b`) scores
  **~93–100% single-pass**. That is *above the ceiling* where extra machinery can
  help — there is no error left for agentic self-correction to fix and no shaky
  signal for swarm voting to lift.
- Result: architectures barely differentiate on accuracy, and monolithic wins on
  cost. Swarm even looked "dominated" — but that is a **task-selection artifact**,
  not a real weakness: self-consistency voting only helps in a moderate-accuracy
  band, and the baseline tasks are too easy to be in it.

The study's pre-registered hypothesis (H, Candidate D) is that architecture
superiority is **task-dependent**. To observe that, the task set must actually
span the regime where it appears. The **frontier tier** adds that regime.

## Where each architecture wins (why the band matters)

| Architecture | Wins when… |
| --- | --- |
| Monolithic | tasks are easy / single-step (nothing to iterate or vote on) |
| Agentic (Executor+Verifier) | single passes make **correctable** errors — hard multi-step, code |
| Swarm (parallel voting) | single-pass accuracy is **moderate (~0.4–0.7)** so aggregating diverse samples lifts it |

Both agentic and swarm need the model to be **near its capability edge** on the
task. Too easy → everyone ties (baseline tier). Too hard → everyone fails. The
interesting, differentiating zone is in between.

## The two tiers

- **baseline** — the frozen v1 suite (`tasks/manifest.json`, 15 items). Objective,
  easy-to-mid difficulty. A legitimate finding in its own right: *on easy tasks,
  architecture doesn't matter — use monolithic.* Unchanged by this amendment.
- **frontier** — `tasks/frontier_manifest.json`. Harder, architecture-favoring,
  still objectively graded (numeric `math`, unit-test `code`, normalized-string
  `multihop`). Every row records `task_tier`, and `harness.analyze` prints a
  **tier × architecture** table so the two regimes are compared directly.

## Selection criterion (pre-declared, empirical)

An item earns a place in the frozen frontier tier **iff**, for the pinned model,
**monolithic single-pass accuracy ∈ ~[0.4, 0.7] at N ≥ 5.** Items the model always
gets right (no headroom) or always wrong (unreachable) are **dropped, not tuned** —
this keeps selection from cherry-picking a favorable story. The candidate items
shipped here are marked `CANDIDATE_UNCALIBRATED` until this measurement is run.

## Calibration procedure

```bash
# 1) Measure monolithic single-pass accuracy per frontier item (N=5).
./.venv/bin/python -m harness.run \
    --manifest tasks/frontier_manifest.json --backend monolithic --trials 5

# 2) Per-item monolithic accuracy — keep items in the ~0.4-0.7 band.
./.venv/bin/python -c "
import json, collections
acc=collections.defaultdict(list)
for l in open('results/local.jsonl'):
    r=json.loads(l)
    if r.get('task_tier')=='frontier' and r['backend']=='monolithic':
        acc[r['task_id']].append(r['correct'])
for t,v in sorted(acc.items()):
    a=sum(v)/len(v); flag='KEEP' if 0.4<=a<=0.7 else 'drop'
    print(f'{t:14} monolithic acc={a:.2f}  {flag}')
"

# 3) Edit frontier_manifest.json to keep only KEEP items, set frozen: true +
#    frozen_on, and log the final item IDs in the pre-reg Amendment Log.

# 4) Full frontier run + judge + analyze (all three backends):
./.venv/bin/python -m harness.run --manifest tasks/frontier_manifest.json --trials 5
./.venv/bin/python -m harness.judge
./.venv/bin/python -m harness.analyze --charts   # tier x architecture table appears
```

If too few items survive, add more candidates (harder math/code, or a real
GAIA L1–L2 / SWE-bench subset) and re-calibrate. The candidate set here is a
starting point, not the frozen tier.

## Self-consistency (already guaranteed)

Every frontier code item ships a `reference_solution`, and `tests/test_frontier_tasks.py`
runs each one through the real grader — so the unit tests are proven correct and
each math/multihop gold answer self-grades. Authoring bugs are caught offline,
before any model runs.
