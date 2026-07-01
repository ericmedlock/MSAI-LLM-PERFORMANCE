"""CLI entrypoint:  python -m harness.run [options]

Reads pinned values from config; only selection (which backends, which
tasks, how many trials, which environment) is chosen here. Idempotent:
re-running tops up missing rows rather than duplicating.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backends.factory import BACKEND_NAMES, build_client
from harness.config import load_config, load_dotenv
from harness.prompts import load_prompts
from harness.runner import RunPlan, Runner
from harness.task_loader import load_tasks


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness.run", description=__doc__)
    p.add_argument("--config", default="config/config.yaml", help="path to config.yaml")
    p.add_argument(
        "--manifest",
        help="task manifest override (default: tasks_manifest from config); "
        "e.g. tasks/frontier_manifest.json to run the frontier tier",
    )
    p.add_argument(
        "--backend",
        action="append",
        choices=BACKEND_NAMES,
        help="backend to run (repeatable); default: all three",
    )
    p.add_argument(
        "--environment",
        help="environment key override (default: active_environment from config)",
    )
    p.add_argument(
        "--task-id",
        action="append",
        help="restrict to specific task id(s) (repeatable); default: all tasks",
    )
    p.add_argument("--trials", type=int, help="override N trials (default: config trials.n)")
    p.add_argument("--output", help="output JSONL path (default: results/<env>.jsonl)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit without calling the model",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    load_dotenv()  # per-machine endpoint/provider/model/key overrides
    config = load_config(args.config)
    prompts = load_prompts(config.prompts_dir)
    all_tasks = load_tasks(args.manifest or config.tasks_manifest)

    environment = args.environment or config.active_environment
    backends = args.backend or list(BACKEND_NAMES)
    trials = args.trials or config.trials_n

    if args.task_id:
        wanted = set(args.task_id)
        tasks = [t for t in all_tasks if t.task_id in wanted]
        missing = wanted - {t.task_id for t in tasks}
        if missing:
            print(f"error: unknown task id(s): {sorted(missing)}", file=sys.stderr)
            return 2
    else:
        tasks = all_tasks

    output = args.output or str(Path(config.results_dir) / f"{environment}.jsonl")
    plan = RunPlan(environment=environment, backends=backends, tasks=tasks, trials=trials)

    total = len(tasks) * len(backends) * trials
    env = config.env(environment).resolved()
    print(f"Environment : {environment} ({env.name})")
    print(f"Provider    : {env.provider} @ {env.base_url}")
    print(f"Model       : {env.model}  [canonical: {config.model.tag} {config.model.quantization}]")
    print(f"Backends    : {', '.join(backends)}")
    tiers = sorted({t.tier for t in tasks})
    print(f"Tasks       : {len(tasks)}  (tier: {', '.join(tiers)})")
    print(f"Trials (N)  : {trials}")
    print(f"Total cells : {total} runs -> {output}")

    if args.dry_run:
        print("\n[dry-run] not calling the model.")
        return 0

    client = build_client(config, environment)
    runner = Runner(config=config, client=client, prompts=prompts)
    written = runner.run_plan(plan, output)
    print(f"\nDone. Wrote {written} new row(s); {total - written} already present.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
