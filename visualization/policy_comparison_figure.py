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
``analysis.layout.iter_combo_summaries`` so the combo-discovery rule stays in one
place.
"""

from pathlib import Path
from typing import List

import matplotlib

matplotlib.use("Agg")  # headless, browser-free static rendering
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from analysis.layout import iter_combo_summaries, split_combo_label
from visualization.figure_style import (
    FIGURE_SIZE_INCHES,
    KG_PER_KILOTONNE,
    POLICY_MARKERS,
    REPRODUCIBLE_PDF_METADATA,
    STRATEGY_COLORS,
    STRATEGY_LABELS,
)
from visualization.visualization_utils import EMISSIONS_METRIC, SERVICE_METRIC, read_metric_intervals


def build_points(path: Path) -> List[dict]:
    """One styled point dict per configuration under scenario dir ``path``.

    Each dict carries the policy, strategy, the service-level and emissions means,
    and their asymmetric 95% CI half-widths (for error bars). Sorted by combo
    label for a deterministic draw order. Returns an empty list if no
    ``summary.csv`` files are found.
    """
    points: List[dict] = []
    for label, summary_path in iter_combo_summaries(path, root=False):
        policy, strategy = split_combo_label(label)
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


def write_policy_comparison_figure(path):
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
    output_path = path / "policy_comparison.pdf"
    fig.savefig(
        output_path,
        metadata=REPRODUCIBLE_PDF_METADATA,
    )
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
