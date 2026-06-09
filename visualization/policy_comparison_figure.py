"""Emissions-vs-service-level policy-comparison figure (the paper's Fig. 2).

One scatter point per policy x strategy configuration over the Monte Carlo
baseline: x is full service level, y is total operational emissions, and each
point carries 95% confidence-interval crosshairs read straight from the combo's
``summary.csv`` (``ci95_low``/``ci95_high``). Marker shape encodes the inventory
policy (PUSH/PULL); colour encodes the stock strategy.

Rendered with Matplotlib's Agg backend, so the PDF is produced in pure Python
with no browser engine -- unlike Plotly's ``write_image``, which drives a
headless Chromium via Kaleido. This is the only figure the paper embeds from the
simulation pipeline (the methodology diagram is hand-drawn), so it is the only
one that needs a browser-free static export.

Reads only ``summary.csv`` files (the Monte Carlo aggregate) and runs via
``python -m visualization.policy_comparison_figure <scenario_dir>``. It reuses
``analysis.pareto.iter_combo_summaries`` so the combo-discovery rule stays in one
place.
"""

import csv
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")  # headless, browser-free static rendering
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from analysis.pareto import iter_combo_summaries

# The two plotted metrics and their summary.csv keys. x is the headline service
# level (full, not operational -- the paper reports the full figure because the
# two coincide when no_capability_lost is zero); y is operational emissions.
SERVICE_METRIC = "service_level_full_pct"
EMISSIONS_METRIC = "total_emissions_kgco2e"

# Emissions are scaled to kilotonnes for a readable axis (raw values run ~1e6-2e7
# kg CO2e). The divisor is exact, so it shifts only the axis label, not the data.
KG_PER_KILOTONNE = 1_000_000.0

# Marker shape per inventory policy, colour per stock strategy (caption convention).
POLICY_MARKERS = {"push": "o", "pull": "^"}
STRATEGY_COLORS = {
    "on_demand": "#1f77b4",
    "reorder_50": "#ff7f0e",
    "reorder_90": "#2ca02c",
}
STRATEGY_LABELS = {
    "on_demand": "ON_DEMAND",
    "reorder_50": "REORDER_50",
    "reorder_90": "REORDER_90",
}

# Single-column journal figure size in inches.
FIGURE_SIZE_INCHES = (7, 5)


def read_metric_intervals(
    summary_csv_path: Path, metrics: List[str]
) -> Dict[str, Tuple[float, float, float]]:
    """Read ``(mean, ci95_low, ci95_high)`` for each requested metric from one ``summary.csv``.

    The file has rows ``metric,mean,stdev,ci95_low,ci95_high,count``. Raises
    ``KeyError`` if a requested metric is absent, so an incomplete dataset fails
    loudly rather than silently dropping a configuration from the figure.
    """
    wanted = set(metrics)
    intervals: Dict[str, Tuple[float, float, float]] = {}
    with open(summary_csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 5 or row[0] not in wanted:
                continue
            intervals[row[0]] = (float(row[1]), float(row[3]), float(row[4]))
    missing = wanted - intervals.keys()
    if missing:
        raise KeyError(
            f"{summary_csv_path}: missing metric(s) {sorted(missing)}"
        )
    return intervals


def _split_combo_label(label: str) -> Tuple[str, str]:
    """Split a ``policy__strategy`` combo label into ``(policy, strategy)``.

    Raises ``ValueError`` on any label that is not exactly one ``__`` join, so an
    unexpected directory name fails loudly instead of mis-styling a point.
    """
    parts = label.split("__")
    if len(parts) != 2:
        raise ValueError(
            f"Expected a 'policy__strategy' combo label, got {label!r}"
        )
    return parts[0], parts[1]


def build_points(path: Path) -> List[dict]:
    """One styled point dict per configuration under scenario dir ``path``.

    Each dict carries the policy, strategy, the service-level and emissions means,
    and their asymmetric 95% CI half-widths (for error bars). Sorted by combo
    label for a deterministic draw order. Returns an empty list if no
    ``summary.csv`` files are found.
    """
    points: List[dict] = []
    for label, summary_path in iter_combo_summaries(path, root=False):
        policy, strategy = _split_combo_label(label)
        intervals = read_metric_intervals(
            summary_path, [SERVICE_METRIC, EMISSIONS_METRIC]
        )
        service_mean, service_low, service_high = intervals[SERVICE_METRIC]
        emis_mean, emis_low, emis_high = intervals[EMISSIONS_METRIC]
        points.append(
            {
                "label": label,
                "policy": policy,
                "strategy": strategy,
                "service": service_mean,
                "service_err": [
                    [service_mean - service_low],
                    [service_high - service_mean],
                ],
                "emissions": emis_mean / KG_PER_KILOTONNE,
                "emissions_err": [
                    [(emis_mean - emis_low) / KG_PER_KILOTONNE],
                    [(emis_high - emis_mean) / KG_PER_KILOTONNE],
                ],
            }
        )
    return points


def _build_legend_handles(points: List[dict]) -> List[Line2D]:
    """Two legend groups: marker shape per policy, colour per strategy.

    Only the policies and strategies actually present in ``points`` are listed, so
    a single-policy dataset does not advertise an absent marker.
    """
    present_policies = [p for p in POLICY_MARKERS if any(pt["policy"] == p for pt in points)]
    present_strategies = [s for s in STRATEGY_COLORS if any(pt["strategy"] == s for pt in points)]
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
    return handles


def render_figure(points: List[dict]):
    """Build the Matplotlib figure for ``points`` and return it (does not save)."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)
    for point in points:
        ax.errorbar(
            point["service"],
            point["emissions"],
            xerr=point["service_err"],
            yerr=point["emissions_err"],
            marker=POLICY_MARKERS[point["policy"]],
            color=STRATEGY_COLORS[point["strategy"]],
            markersize=9,
            elinewidth=1.0,
            capsize=3,
            linestyle="none",
        )
    ax.set_xlabel("Full service level (%)")
    ax.set_ylabel("Total emissions (kt CO$_2$e)")
    ax.set_title("Emissions vs service level across policy configurations")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(handles=_build_legend_handles(points), loc="best", fontsize=9)
    fig.tight_layout()
    return fig


def write_policy_comparison_figure(path, filename: str = "policy_comparison.pdf"):
    """Render and save the policy-comparison PDF under scenario dir ``path``.

    Returns the written ``Path``, or ``None`` if no ``summary.csv`` files exist
    under ``path``. The PDF is a vector export from Matplotlib's Agg backend, so
    no browser/Kaleido is involved.
    """
    path = Path(path)
    points = build_points(path)
    if not points:
        return None
    fig = render_figure(points)
    output_path = path / filename
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Emissions-vs-service-level policy-comparison figure (browser-free PDF)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help="Scenario dir holding {combo}/summary.csv (default: the Baseline scenario).",
    )
    args = parser.parse_args()

    target = Path(args.path)
    written = write_policy_comparison_figure(target)
    if written is None:
        raise SystemExit(f"No summary.csv files found under {target}")
    print(f"Wrote {written}")
