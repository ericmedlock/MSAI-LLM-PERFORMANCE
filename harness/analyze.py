"""CLI:  python -m harness.analyze [--results ...] [--output ...] [--charts]

Reads committed telemetry rows and writes a Markdown analysis report. Because
it consumes only the raw JSONL, every figure is reproducible from committed
data.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

from harness.analysis import load_records
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
        "--charts",
        action="store_true",
        help="also write PNG Pareto charts (requires matplotlib)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = sorted(glob.glob(args.results)) or [args.results]
    records = load_records(paths)

    report = build_report(records)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    print(f"Read {len(records)} row(s) from {len(paths)} file(s).")
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
