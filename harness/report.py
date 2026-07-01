"""Render an analysis report (Markdown) from telemetry rows.

Produces the tables the pre-registration declares (S9): per-architecture
mean+/-std for every metric, per-cell breakdown, accuracy-vs-latency and
accuracy-vs-tokens Pareto frontiers, and an error distribution. Optional PNG
charts are written iff matplotlib is available; their absence is not an error.
"""

from __future__ import annotations

from pathlib import Path

from harness.analysis import (
    CellSummary,
    error_distribution,
    pareto_frontier,
    summarize,
)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join([line, sep, body]) if rows else line + "\n" + sep


def _agg_rows(summaries: list[CellSummary], label_keys: tuple[str, ...]) -> list[list[str]]:
    rows = []
    for s in summaries:
        rows.append(
            [
                s.label(label_keys),
                str(s.n),
                f"{s.accuracy * 100:.0f}%",
                s.latency_s.fmt("s"),
                s.total_tokens.fmt(places=0),
                s.action_count.fmt(places=1),
                s.tokens_per_s.fmt(places=1),
            ]
        )
    return rows


def build_report(records: list[dict], host_profiles: list[dict] | None = None) -> str:
    if not records:
        return "# Analysis\n\n_No result rows found._\n"

    environments = sorted({r.get("environment") for r in records})
    models = sorted({r.get("model_tag") for r in records})
    n = len(records)

    out: list[str] = []
    out.append("# Benchmark Analysis\n")
    out.append(
        f"- Runs: **{n}**  ·  Environments: **{', '.join(map(str, environments))}**  "
        f"·  Model: **{', '.join(map(str, models))}**"
    )
    for hp in host_profiles or []:
        hw = hp.get("hardware", {})
        out.append(
            f"- Host (`{hp.get('environment')}`): **{hw.get('chip')}**, "
            f"{hw.get('total_ram_gb')} GB RAM"
            + (f" (unified/VRAM {hw.get('total_vram_gb')} GB)" if hw.get('unified_memory')
               else f", GPU {hw.get('gpu_model')} {hw.get('total_vram_gb')} GB VRAM")
            + f", {hp.get('os')} · serving {hp.get('serving', {}).get('provider')} "
            f"`{hp.get('serving', {}).get('backend_model')}`"
        )
    out.append(
        "- Every metric is mean±std across trials (pre-reg S9). "
        "Pareto: minimize latency/tokens, maximize accuracy.\n"
    )

    metric_header = ["group", "n", "acc", "latency", "tokens(tot)", "actions", "tok/s"]

    # 1) Per-architecture, split by environment when more than one is present.
    if len(environments) > 1:
        out.append("## By architecture × environment\n")
        summaries = summarize(records, ("environment", "backend"))
        out.append(_table(metric_header, _agg_rows(summaries, ("environment", "backend"))))
    else:
        out.append("## By architecture\n")
        summaries = summarize(records, ("backend",))
        out.append(_table(metric_header, _agg_rows(summaries, ("backend",))))
    out.append("")

    # 1b) Per-tier × architecture — the key view for "does architecture matter
    # on architecture-favoring tasks?" Only shown when >1 tier is present.
    tiers = sorted({r.get("task_tier", "baseline") for r in records})
    if len(tiers) > 1:
        out.append("## By tier × architecture\n")
        tier_summ = summarize(records, ("task_tier", "backend"))
        out.append(_table(metric_header, _agg_rows(tier_summ, ("task_tier", "backend"))))
        out.append("")

    # 2) Per-cell (backend × task).
    out.append("## By architecture × task\n")
    cells = summarize(records, ("task_id", "backend"))
    out.append(_table(metric_header, _agg_rows(cells, ("task_id", "backend"))))
    out.append("")

    # 3) Pareto frontiers at architecture level (per environment).
    out.append("## Pareto frontiers (architecture level)\n")
    for env in environments:
        env_records = [r for r in records if r.get("environment") == env]
        by_backend = summarize(env_records, ("backend",))
        points = [
            {
                "backend": s.keys["backend"],
                "accuracy": s.accuracy,
                "latency": s.latency_s.mean,
                "tokens": s.total_tokens.mean,
            }
            for s in by_backend
        ]
        lat_front = {p["backend"] for p in pareto_frontier(points, "latency", "accuracy")}
        tok_front = {p["backend"] for p in pareto_frontier(points, "tokens", "accuracy")}
        rows = [
            [
                p["backend"],
                f"{p['accuracy'] * 100:.0f}%",
                f"{p['latency']:.1f}s",
                f"{p['tokens']:.0f}",
                "✓" if p["backend"] in lat_front else "",
                "✓" if p["backend"] in tok_front else "",
            ]
            for p in points
        ]
        out.append(f"**{env}**\n")
        out.append(
            _table(
                ["backend", "acc", "latency", "tokens", "acc·vs·latency", "acc·vs·tokens"],
                rows,
            )
        )
        out.append("")

    # 3b) LLM-as-judge secondary metrics (only if judge data was joined in).
    judged = summarize([r for r in records if r.get("judge_correct") is not None], ("backend",))
    if judged:
        out.append("## LLM-as-judge (secondary metric)\n")
        out.append(
            "_Different-family judge model; quality 0–max, and agreement with the "
            "primary auto-grader._\n"
        )
        rows = [
            [
                s.keys["backend"],
                str(s.judge_quality.n),
                s.judge_quality.fmt(places=2),
                f"{s.judge_correct_rate * 100:.0f}%" if s.judge_correct_rate is not None else "—",
                f"{s.judge_agreement * 100:.0f}%" if s.judge_agreement is not None else "—",
            ]
            for s in judged
        ]
        out.append(
            _table(["backend", "n", "quality", "judge·correct", "agree·w/·auto"], rows)
        )
        out.append("")

    # 4) Error distribution by architecture.
    out.append("## Error distribution by architecture\n")
    dist = error_distribution(records, "backend")
    if not dist:
        out.append("_No failures recorded._\n")
    else:
        cats = sorted({c for d in dist.values() for c in d})
        rows = [[b] + [str(dist[b].get(c, 0)) for c in cats] for b in sorted(dist)]
        out.append(_table(["backend"] + cats, rows))
    out.append("")

    return "\n".join(out)


def write_charts(records: list[dict], out_dir: str | Path) -> list[Path]:
    """Write accuracy-vs-latency and accuracy-vs-tokens scatter PNGs.

    Returns the paths written. If matplotlib is not installed, returns [] --
    the Markdown report is the primary, dependency-free deliverable.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_backend = summarize(records, ("backend",))
    written: list[Path] = []

    for x_attr, x_label, fname in [
        ("latency_s", "latency (s)", "pareto_accuracy_vs_latency.png"),
        ("total_tokens", "total tokens", "pareto_accuracy_vs_tokens.png"),
    ]:
        fig, ax = plt.subplots(figsize=(6, 4))
        for s in by_backend:
            x = getattr(s, x_attr).mean
            ax.scatter(x, s.accuracy * 100, s=80)
            ax.annotate(s.keys["backend"], (x, s.accuracy * 100),
                        textcoords="offset points", xytext=(6, 4))
        ax.set_xlabel(x_label)
        ax.set_ylabel("accuracy (%)")
        ax.set_title(f"accuracy vs {x_label}")
        ax.grid(True, alpha=0.3)
        path = out_dir / fname
        fig.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written.append(path)
    return written
