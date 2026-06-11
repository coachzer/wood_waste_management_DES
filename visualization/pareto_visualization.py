"""Pareto frontier figure: emissions vs service level with frontier overlay.

A 2D scatter in the same visual language as the policy-comparison figure
(marker shape for policy, colour for strategy, CI crosshairs from
``summary.csv``), with the Pareto non-dominated frontier drawn as a
connecting line through frontier points. Dominated points are rendered
faded and smaller; frontier points are bold. A small inset table shows
the two remaining objectives (landfill, cost) for each frontier
configuration so the four-objective context is not lost.

Rendered with Matplotlib's Agg backend (browser-free static PDF), just
like the policy-comparison figure.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from analysis.pareto import OBJECTIVES, build_pareto_report, iter_combo_summaries
from visualization.policy_comparison_figure import (
    FIGURE_SIZE_INCHES,
    KG_PER_KILOTONNE,
    POLICY_MARKERS,
    STRATEGY_COLORS,
    STRATEGY_LABELS,
    read_metric_intervals,
)

SERVICE_METRIC = "service_level_full_pct"
EMISSIONS_METRIC = "total_emissions_kgco2e"
LANDFILL_METRIC = "landfill_volume_m3"
COST_METRIC = "total_system_cost"


def _split_combo_label(label: str) -> Tuple[str, str]:
    parts = label.split("__")
    if len(parts) != 2:
        raise ValueError(
            f"Expected a 'policy__strategy' combo label, got {label!r}"
        )
    return parts[0], parts[1]


def _build_points(
    path: Path,
    root: bool,
    objectives: List[Tuple[str, str]],
) -> List[dict]:
    """One styled point dict per configuration with Pareto status and CI data.

    Merges the Pareto frontier report (means + non_dominated flag) with the
    CI intervals from each combo's ``summary.csv``.
    """
    pareto_rows = build_pareto_report(path, root=root, objectives=objectives)
    if not pareto_rows:
        return []

    frontier_set = {row["config"] for row in pareto_rows if row["non_dominated"]}
    pareto_by_config = {row["config"]: row for row in pareto_rows}

    all_metrics = [SERVICE_METRIC, EMISSIONS_METRIC, LANDFILL_METRIC, COST_METRIC]

    points: List[dict] = []
    for label, summary_path in iter_combo_summaries(path, root=root):
        if label not in pareto_by_config:
            continue
        policy, strategy = _split_combo_label(label)

        intervals = read_metric_intervals(summary_path, all_metrics)
        service_mean, service_low, service_high = intervals[SERVICE_METRIC]
        emis_mean, emis_low, emis_high = intervals[EMISSIONS_METRIC]
        landfill_mean = intervals[LANDFILL_METRIC][0]
        cost_mean = intervals[COST_METRIC][0]

        points.append(
            {
                "label": label,
                "policy": policy,
                "strategy": strategy,
                "frontier": label in frontier_set,
                "service": service_mean,
                "service_err": [
                    [max(0.0, service_mean - service_low)],
                    [max(0.0, service_high - service_mean)],
                ],
                "emissions": emis_mean / KG_PER_KILOTONNE,
                "emissions_err": [
                    [max(0.0, (emis_mean - emis_low) / KG_PER_KILOTONNE)],
                    [max(0.0, (emis_high - emis_mean) / KG_PER_KILOTONNE)],
                ],
                "landfill": landfill_mean,
                "cost": cost_mean,
            }
        )
    return points


def _build_legend_handles(points: List[dict]) -> List[Line2D]:
    present_policies = [
        p for p in POLICY_MARKERS if any(pt["policy"] == p for pt in points)
    ]
    present_strategies = [
        s for s in STRATEGY_COLORS if any(pt["strategy"] == s for pt in points)
    ]
    handles: List[Line2D] = []
    for policy in present_policies:
        handles.append(
            Line2D(
                [], [], color="black", marker=POLICY_MARKERS[policy],
                linestyle="none", markersize=8, label=policy.upper(),
            )
        )
    for strategy in present_strategies:
        handles.append(
            Line2D(
                [], [], color=STRATEGY_COLORS[strategy], marker="s",
                linestyle="none", markersize=8, label=STRATEGY_LABELS[strategy],
            )
        )
    handles.append(
        Line2D(
            [], [], color="black", linestyle="-", linewidth=1.5,
            marker="none", label="Pareto frontier",
        )
    )
    return handles


def build_pareto_figure(
    points: List[dict],
):
    """Build the Matplotlib figure and return it (does not save)."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)

    frontier_pts = sorted(
        [p for p in points if p["frontier"]], key=lambda p: p["service"]
    )
    dominated_pts = [p for p in points if not p["frontier"]]

    for point in dominated_pts:
        ax.errorbar(
            point["service"],
            point["emissions"],
            xerr=point["service_err"],
            yerr=point["emissions_err"],
            marker=POLICY_MARKERS[point["policy"]],
            color=STRATEGY_COLORS[point["strategy"]],
            markersize=6,
            alpha=0.35,
            elinewidth=0.7,
            capsize=2,
            linestyle="none",
        )

    for point in frontier_pts:
        ax.errorbar(
            point["service"],
            point["emissions"],
            xerr=point["service_err"],
            yerr=point["emissions_err"],
            marker=POLICY_MARKERS[point["policy"]],
            color=STRATEGY_COLORS[point["strategy"]],
            markersize=10,
            elinewidth=1.2,
            capsize=3,
            linestyle="none",
            zorder=5,
        )

    if len(frontier_pts) >= 2:
        ax.plot(
            [p["service"] for p in frontier_pts],
            [p["emissions"] for p in frontier_pts],
            color="black",
            linewidth=1.5,
            linestyle="-",
            alpha=0.6,
            zorder=4,
        )

    if frontier_pts:
        col_labels = ["Config", "Landfill (m³)", "Cost"]
        cell_text = []
        for p in frontier_pts:
            cell_text.append([
                f"{p['policy'].upper()} / {STRATEGY_LABELS[p['strategy']]}",
                f"{p['landfill']:,.0f}",
                f"{p['cost']:,.0f}",
            ])
        table = ax.table(
            cellText=cell_text,
            colLabels=col_labels,
            loc="lower left",
            cellLoc="center",
            bbox=[0.02, 0.02, 0.48, 0.06 + 0.045 * len(frontier_pts)],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        for key, cell in table.get_celld().items():
            cell.set_edgecolor("#cccccc")
            cell.set_linewidth(0.5)
            if key[0] == 0:
                cell.set_facecolor("#f0f0f0")
                cell.set_text_props(weight="bold")
            else:
                cell.set_facecolor("white")
                cell.set_alpha(0.85)

    ax.set_xlabel("Full service level (%)")
    ax.set_ylabel("Total emissions (kt CO$_2$e)")
    ax.set_title("Pareto frontier: emissions vs service level")
    ax.grid(True, linestyle=":", alpha=0.5)

    n_frontier = sum(1 for p in points if p["frontier"])
    ax.text(
        0.98, 0.98,
        f"{n_frontier} of {len(points)} non-dominated",
        transform=ax.transAxes,
        ha="right", va="top",
        fontsize=8, color="#666666",
    )

    ax.legend(handles=_build_legend_handles(points), loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


def write_pareto_plot(
    path,
    root: bool = False,
    objectives: List[Tuple[str, str]] = OBJECTIVES,
    filename: str = "pareto_frontier.pdf",
):
    """Render and save the Pareto frontier PDF under ``path``.

    Returns the written ``Path``, or ``None`` if no ``summary.csv`` files
    exist under ``path``.
    """
    path = Path(path)
    points = _build_points(path, root=root, objectives=objectives)
    if not points:
        return None
    fig = build_pareto_figure(points)
    output_path = path / filename
    fig.savefig(
        output_path,
        metadata={
            "CreationDate": datetime(1970, 1, 1, 0, 0, 0),
            "ModDate": datetime(1970, 1, 1, 0, 0, 0),
        },
    )
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Pareto frontier figure: emissions vs service level (browser-free PDF)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help="Scenario dir holding {combo}/summary.csv (default: the Baseline scenario).",
    )
    args = parser.parse_args()

    target = Path(args.path)
    written = write_pareto_plot(target)
    if written is None:
        raise SystemExit(f"No summary.csv files found under {target}")
    print(f"Wrote {written}")
