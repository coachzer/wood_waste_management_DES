"""Pareto frontier over the multi-objective KPI vector across configurations.

Ranking configurations on each KPI separately hides trade-offs: a combo can win
on cost precisely because it under-processes (PULL/on_demand's "lowest cost" is a
56.9%-service artifact, not a free lunch). The Pareto frontier reports the
non-dominated set over the joint objective vector instead -- which configurations
are not beaten on every objective at once -- so a dominated corner cannot pass for
a winner.

This is an analysis-layer reduction over the Monte Carlo dataset: it reads each
combo's already-written ``summary.csv`` ``mean`` column (one point per
configuration) and computes domination. There is no simulation change and no new
per-run KPI, so the golden additive gate is unaffected.

This module reads only ``summary.csv`` files and runs via
``python -m analysis.pareto <dir>`` (the Plotly companion plot is imported lazily
inside ``__main__`` only, so a missing visualization dependency does not break the
CSV artifact). ``main.py`` imports ``write_pareto_report`` by module path, the same
way it imports ``write_paired_comparison_report``.
"""

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# The objective vector: each entry is ``(summary.csv metric key, sense)`` where
# sense is "max" (higher is better, e.g. service level) or "min" (lower is
# better, e.g. emissions/landfill/cost). Kept in-module rather than in
# config/constants.py: it is this report's objective definition, not a
# project-wide constant.
OBJECTIVES: List[Tuple[str, str]] = [
    ("service_level_full_pct", "max"),
    ("total_emissions_kgco2e", "min"),
    ("landfill_volume_m3", "min"),
    ("total_system_cost", "min"),
]


def _goodness(value: float, sense: str) -> float:
    """Map a raw objective value to a 'higher is better' scale.

    Negating the minimize objectives lets domination be expressed uniformly as
    ">= on all, > on at least one", with no per-objective sense branching in the
    comparison itself.
    """
    if sense == "max":
        return value
    if sense == "min":
        return -value
    raise ValueError(f"Unknown objective sense {sense!r} (expected 'max' or 'min')")


def dominates(
    point_a: Dict[str, float],
    point_b: Dict[str, float],
    objectives: List[Tuple[str, str]] = OBJECTIVES,
) -> bool:
    """Whether configuration A Pareto-dominates B over ``objectives``.

    A dominates B iff A is at least as good as B on every objective (sense-aware)
    AND strictly better on at least one. Two configurations with identical
    objective vectors do not dominate each other (no strict improvement exists),
    so both are retained on the frontier. Comparison is exact: the ``summary.csv``
    source is already ``%.6g``-formatted, so equality is deterministic and a float
    tolerance would only blur genuinely distinct points.
    """
    strictly_better_somewhere = False
    for metric, sense in objectives:
        goodness_a = _goodness(point_a[metric], sense)
        goodness_b = _goodness(point_b[metric], sense)
        if goodness_a < goodness_b:
            return False
        if goodness_a > goodness_b:
            strictly_better_somewhere = True
    return strictly_better_somewhere


def pareto_frontier(
    points: Dict[str, Dict[str, float]],
    objectives: List[Tuple[str, str]] = OBJECTIVES,
) -> List[str]:
    """Labels of the non-dominated configurations, sorted for determinism.

    ``points`` maps a configuration label to its objective vector. A label is on
    the frontier iff no other configuration dominates it.
    """
    return sorted(
        label
        for label in points
        if not any(
            dominates(points[other], points[label], objectives)
            for other in points
            if other != label
        )
    )


def iter_combo_summaries(path: Path, root: bool) -> Iterable[Tuple[str, Path]]:
    """Yield ``(config_label, summary_csv_path)`` for each configuration under ``path``.

    Scenario mode (``root=False``): ``path`` is a scenario dir; each immediate
    subdir is a combo holding ``summary.csv``; the label is the combo name
    (e.g. ``push__on_demand``). Root mode (``root=True``): ``path`` holds scenario
    dirs, each holding combo dirs; the label is ``{scenario}__{combo}`` so the
    frontier spans (scenario x combo) -- e.g. Baseline plus the C1 Buffer
    scenarios in one frontier. Sorted so the artifact is deterministic.
    """
    glob_pattern = "*/*/summary.csv" if root else "*/summary.csv"
    for summary_path in sorted(path.glob(glob_pattern)):
        combo_dir = summary_path.parent
        if root:
            label = f"{combo_dir.parent.name}__{combo_dir.name}"
        else:
            label = combo_dir.name
        yield label, summary_path


def read_objective_point(
    summary_csv_path: Path,
    objectives: List[Tuple[str, str]] = OBJECTIVES,
) -> Dict[str, float]:
    """Read the ``mean`` of each objective metric from one ``summary.csv``.

    The file has rows ``metric,mean,stdev,ci95_low,ci95_high,count``. Raises
    ``KeyError`` if a requested objective metric is absent, so a malformed or
    incomplete dataset fails loudly rather than producing a silently partial
    frontier.
    """
    wanted = {metric for metric, _ in objectives}
    means: Dict[str, float] = {}
    with open(summary_csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # skip header: metric,mean,stdev,ci95_low,ci95_high,count
        for row in reader:
            if len(row) < 2 or row[0] not in wanted:
                continue
            means[row[0]] = float(row[1])
    missing = wanted - means.keys()
    if missing:
        raise KeyError(
            f"{summary_csv_path}: missing objective metric(s) {sorted(missing)}"
        )
    return means


def build_pareto_report(
    path: Path,
    root: bool = False,
    objectives: List[Tuple[str, str]] = OBJECTIVES,
) -> List[dict]:
    """One row dict per configuration: its objective means plus a ``non_dominated`` flag.

    Returns an empty list when no ``summary.csv`` files are found under ``path``.
    Rows are sorted by config label.
    """
    points = {
        label: read_objective_point(summary_path, objectives)
        for label, summary_path in iter_combo_summaries(path, root)
    }
    if not points:
        return []
    frontier = set(pareto_frontier(points, objectives))
    rows: List[dict] = []
    for label in sorted(points):
        row = {"config": label}
        row.update({metric: points[label][metric] for metric, _ in objectives})
        row["non_dominated"] = label in frontier
        rows.append(row)
    return rows


def write_pareto_report(
    path,
    root: bool = False,
    objectives: List[Tuple[str, str]] = OBJECTIVES,
):
    """Write ``pareto_frontier.csv`` under ``path`` and return its ``Path``.

    Returns ``None`` when there is nothing to compare (no ``summary.csv`` files).
    The artifact lives beside ``paired_comparison.csv`` in scenario mode, or at
    the dataset root in ``--root`` mode.
    """
    path = Path(path)
    rows = build_pareto_report(path, root=root, objectives=objectives)
    if not rows:
        return None

    metric_columns = [metric for metric, _ in objectives]
    header = ["config"] + metric_columns + ["non_dominated"]
    lines = [",".join(header)]
    for row in rows:
        values = [row["config"]]
        values.extend(f"{row[metric]:.6g}" for metric in metric_columns)
        values.append(str(row["non_dominated"]))
        lines.append(",".join(values))

    report_path = path / "pareto_frontier.csv"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _print_frontier_summary(rows: List[dict]) -> None:
    """Console digest: the non-dominated configurations and their objectives."""
    frontier = [row for row in rows if row["non_dominated"]]
    print(
        f"{len(frontier)} of {len(rows)} configurations are Pareto non-dominated "
        f"over {[metric for metric, _ in OBJECTIVES]}:"
    )
    for row in frontier:
        objective_str = ", ".join(
            f"{metric}={row[metric]:.4g}" for metric, _ in OBJECTIVES
        )
        print(f"  {row['config']}  ({objective_str})")


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Pareto frontier over (service, emissions, landfill, cost) across configurations."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help="Scenario dir holding {combo}/summary.csv (default), or a dataset root with --root.",
    )
    parser.add_argument(
        "--root",
        action="store_true",
        help="Treat path as a dataset root of scenario dirs; pool (scenario x combo) into one frontier.",
    )
    args = parser.parse_args()

    target = Path(args.path)
    report_rows = build_pareto_report(target, root=args.root)
    if not report_rows:
        raise SystemExit(f"No summary.csv files found under {target}")
    report = write_pareto_report(target, root=args.root)
    print(f"Wrote {report}")
    _print_frontier_summary(report_rows)

    # Companion parallel-coordinates HTML. Imported lazily so a missing optional
    # plotting dependency only skips the plot with a note -- the CSV above still
    # stands as the analysis artifact.
    try:
        from visualization.pareto_visualization import write_pareto_plot

        plot = write_pareto_plot(target, root=args.root)
        if plot is not None:
            print(f"Wrote {plot}")
    except Exception as exc:
        print(f"(skipped Pareto plot: {exc})")
