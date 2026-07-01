"""CLI:  python -m harness.analyze [--results ...] [--output ...] [--charts]

Reads committed telemetry rows and writes a Markdown analysis report. Because
it consumes only the raw JSONL, every figure is reproducible from committed
data.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

from harness.analysis import join_judge, load_judge, load_records
from harness.report import build_report, write_charts


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness.analyze", description=__doc__)
    p.add_argument(
        "--results",
        default="results/*.jsonl",
        help="glob or path(s) to result JSONL files (default: results/*.jsonl)",
    )
    p.add_argument(
        "--output",
        default="results/analysis.md",
        help="Markdown report output path (default: results/analysis.md)",
    )
    p.add_argument(
        "--judge",
        default="results/judge/*.jsonl",
        help="glob for judge rows to join in (default: results/judge/*.jsonl)",
    )
    p.add_argument(
        "--charts",
        action="store_true",
        help="also write PNG Pareto charts (requires matplotlib)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = [p for p in (sorted(glob.glob(args.results)) or [args.results]) if "/judge/" not in p]
    records = load_records(paths)

    judge_paths = sorted(glob.glob(args.judge))
    judge_rows = load_judge(judge_paths)
    if judge_rows:
        records = join_judge(records, judge_rows)

    report = build_report(records)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    print(f"Read {len(records)} row(s) from {len(paths)} file(s); {len(judge_rows)} judge row(s).")
    print(f"Wrote report -> {out}")
    if args.charts:
        charts = write_charts(records, out.parent / "charts")
        if charts:
            print("Wrote charts:")
            for c in charts:
                print(f"  - {c}")
        else:
            print("Charts skipped (matplotlib not installed).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
