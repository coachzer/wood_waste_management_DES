"""Per-family figures for the bullwhip, residence, and carbon KPI namespaces.

VIZ-REVIEW T6: these three KPI families are headline thesis results (the
bullwhip verdict; Little's-Law residence times; the three orthogonal carbon
lines of ADR 0011) yet reached only summary.csv and the paired/dominance
reports — no figure. Each producer here reads the per-combo ``summary.csv``
mean + 95% CI rows and renders one browser-free Matplotlib (Agg) PDF, the same
pattern as ``policy_comparison_figure`` (which remains the paper's Fig. 2).

Reads only ``summary.csv`` files and runs standalone via
``python -m visualization.kpi_family_figures <scenario_dir>``. Combo discovery
and CSV parsing are reused from ``analysis.pareto`` and
``policy_comparison_figure`` so those rules stay in one place.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")  # headless, browser-free static rendering

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from analysis.pareto import iter_combo_summaries
from visualization.policy_comparison_figure import (
    FIGURE_SIZE_INCHES,
    STRATEGY_COLORS,
    STRATEGY_LABELS,
    _split_combo_label,
    read_metric_intervals,
)

# The six CV^2-ratio bullwhip keys (ADR 0004-0007) in display order: the
# anchored headline pair, the pooled robustness pair, then the stage-by-stage
# diagnostic. The generation floor is the seventh family key but is
# policy-invariant by construction (ADR 0005), so it renders as a figure
# annotation rather than six identical bars.
BULLWHIP_RATIO_METRICS = [
    "bullwhip.treatment_anchored",
    "bullwhip.collector_anchored",
    "bullwhip.treatment_anchored_pooled",
    "bullwhip.collector_anchored_pooled",
    "bullwhip.treatment_stage",
    "bullwhip.collector_stage",
]
BULLWHIP_FLOOR_METRIC = "bullwhip.generation_floor_cv2"

# Little's-Law residence times (C4): the per-stage headline of the family. WIP
# and throughput are the law's inputs and stay table-only; the derived W is the
# figure. Display order follows the material flow, total last.
RESIDENCE_METRICS = [
    "residence.generator_residence_days",
    "residence.collector_residence_days",
    "residence.treatment_residence_days",
    "residence.total_storage_residence_days",
]
RESIDENCE_METRIC_LABELS = {
    "residence.generator_residence_days": "Generator",
    "residence.collector_residence_days": "Collector",
    "residence.treatment_residence_days": "Treatment",
    "residence.total_storage_residence_days": "Total\n(all stages)",
}

# The three orthogonal carbon lines (ADR 0011), reported side by side and never
# netted: operational emissions (+), avoided emissions (+, a benefit on its own
# system boundary), biogenic carbon stored (negative = sequestered).
CARBON_METRICS = [
    "total_emissions_kgco2e",
    "carbon.avoided_emissions_total_kgco2e",
    "carbon.biogenic_carbon_stored_total_kgco2e",
]
CARBON_METRIC_LABELS = {
    "total_emissions_kgco2e": "Operational emissions",
    "carbon.avoided_emissions_total_kgco2e": "Avoided emissions",
    "carbon.biogenic_carbon_stored_total_kgco2e": "Biogenic carbon stored",
}
CARBON_METRIC_COLORS = {
    "total_emissions_kgco2e": "#d62728",
    "carbon.avoided_emissions_total_kgco2e": "#1f77b4",
    "carbon.biogenic_carbon_stored_total_kgco2e": "#2ca02c",
}

# Carbon values are scaled to kilotonnes for a readable axis, same divisor as
# the policy comparison figure's emissions axis.
KG_PER_KILOTONNE = 1_000_000.0


def to_kilotonnes(interval: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Scale a ``(mean, ci95_low, ci95_high)`` triple from kg to kilotonnes."""
    mean, low, high = interval
    return (
        mean / KG_PER_KILOTONNE,
        low / KG_PER_KILOTONNE,
        high / KG_PER_KILOTONNE,
    )
BULLWHIP_METRIC_LABELS = {
    "bullwhip.treatment_anchored": "Treatment\nanchored",
    "bullwhip.collector_anchored": "Collector\nanchored",
    "bullwhip.treatment_anchored_pooled": "Treatment\npooled",
    "bullwhip.collector_anchored_pooled": "Collector\npooled",
    "bullwhip.treatment_stage": "Treatment\nstage",
    "bullwhip.collector_stage": "Collector\nstage",
}

# Bar styling: colour encodes the stock strategy (same palette as the policy
# comparison figure); fill encodes the inventory policy (solid PUSH, hatched
# PULL) since bars cannot carry the marker-shape convention.
PULL_HATCH = "//"


def _bar_style(row: dict) -> dict:
    return {
        "color": STRATEGY_COLORS[row["strategy"]],
        "hatch": PULL_HATCH if row["policy"] == "pull" else None,
        "edgecolor": "black",
        "linewidth": 0.5,
    }


def _grouped_bar_legend(table: List[dict]) -> List[Patch]:
    """Strategy colours plus the solid/hatched policy encoding, present-only."""
    handles: List[Patch] = []
    for strategy, color in STRATEGY_COLORS.items():
        if any(row["strategy"] == strategy for row in table):
            handles.append(Patch(facecolor=color, label=STRATEGY_LABELS[strategy]))
    for policy, hatch in (("push", None), ("pull", PULL_HATCH)):
        if any(row["policy"] == policy for row in table):
            handles.append(
                Patch(
                    facecolor="white",
                    edgecolor="black",
                    hatch=hatch,
                    label=policy.upper(),
                )
            )
    return handles


def _grouped_bars(ax, table: List[dict], metrics: List[str]) -> None:
    """One bar group per metric, one bar per combo, asymmetric 95% CI whiskers."""
    group_width = 0.8
    bar_width = group_width / len(table)
    for combo_index, row in enumerate(table):
        positions = [
            group_index - group_width / 2 + (combo_index + 0.5) * bar_width
            for group_index in range(len(metrics))
        ]
        means = [row["values"][metric][0] for metric in metrics]
        err_low = [
            row["values"][metric][0] - row["values"][metric][1] for metric in metrics
        ]
        err_high = [
            row["values"][metric][2] - row["values"][metric][0] for metric in metrics
        ]
        ax.bar(
            positions,
            means,
            width=bar_width,
            yerr=[err_low, err_high],
            capsize=2,
            error_kw={"elinewidth": 0.8},
            **_bar_style(row),
        )
    ax.set_xticks(range(len(metrics)))


def build_metric_table(path: Path, metrics: List[str]) -> List[dict]:
    """One row per configuration under scenario dir ``path``.

    Each row carries the combo label, policy, strategy, and a ``values`` dict
    of ``metric -> (mean, ci95_low, ci95_high)`` for every requested metric.
    Missing metrics raise ``KeyError`` (via ``read_metric_intervals``) so an
    incomplete dataset fails loudly. Sorted by combo label for a deterministic
    draw order; empty list if no ``summary.csv`` files are found.
    """
    table: List[dict] = []
    for label, summary_path in iter_combo_summaries(Path(path), root=False):
        policy, strategy = _split_combo_label(label)
        intervals = read_metric_intervals(summary_path, metrics)
        table.append(
            {
                "label": label,
                "policy": policy,
                "strategy": strategy,
                "values": intervals,
            }
        )
    return table


def write_bullwhip_figure(path, filename: str = "bullwhip_comparison.pdf"):
    """Render and save the bullwhip-family PDF under scenario dir ``path``.

    Grouped bars (one group per CV^2-ratio key, one bar per combo) on a log
    axis — the anchored headline ratios run two to three orders of magnitude
    above the stage diagnostics. The dashed line at 1.0 marks no amplification;
    the policy-invariant generation floor is annotated as text. Returns the
    written ``Path``, or ``None`` if no ``summary.csv`` files exist.
    """
    path = Path(path)
    table = build_metric_table(
        path, BULLWHIP_RATIO_METRICS + [BULLWHIP_FLOOR_METRIC]
    )
    if not table:
        return None

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)
    _grouped_bars(ax, table, BULLWHIP_RATIO_METRICS)
    ax.set_xticklabels(
        [BULLWHIP_METRIC_LABELS[metric] for metric in BULLWHIP_RATIO_METRICS],
        fontsize=8,
    )
    ax.set_yscale("log")
    ax.axhline(1.0, color="grey", linestyle="--", linewidth=0.8)
    ax.set_ylabel("CV$^2$ ratio (log scale)")
    ax.set_title("Throughput bullwhip across policy configurations")
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    floor_mean = table[0]["values"][BULLWHIP_FLOOR_METRIC][0]
    ax.set_xlabel(
        "Generation source-variance floor (policy-invariant): "
        f"CV$^2$ = {floor_mean:.3g}",
        fontsize=8,
        color="dimgrey",
    )
    ax.legend(handles=_grouped_bar_legend(table), loc="best", fontsize=8)
    fig.tight_layout()
    output_path = path / filename
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def write_residence_figure(path, filename: str = "residence_comparison.pdf"):
    """Render and save the residence-time PDF under scenario dir ``path``.

    Grouped bars of time-averaged residence days (Little's Law, ``W = L/λ``)
    per stage, one bar per combo, with 95% CI whiskers. Returns the written
    ``Path``, or ``None`` if no ``summary.csv`` files exist.
    """
    path = Path(path)
    table = build_metric_table(path, RESIDENCE_METRICS)
    if not table:
        return None

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)
    _grouped_bars(ax, table, RESIDENCE_METRICS)
    ax.set_xticklabels(
        [RESIDENCE_METRIC_LABELS[metric] for metric in RESIDENCE_METRICS]
    )
    ax.set_ylabel("Time-weighted residence (days)")
    ax.set_title("Per-stage residence time across policy configurations")
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    ax.legend(handles=_grouped_bar_legend(table), loc="best", fontsize=8)
    fig.tight_layout()
    output_path = path / filename
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def write_carbon_figure(path, filename: str = "carbon_comparison.pdf"):
    """Render and save the three-carbon-lines PDF under scenario dir ``path``.

    One bar group per combo, three bars per group — operational emissions,
    avoided emissions, biogenic carbon stored — in kt CO2e with 95% CI
    whiskers, around a zero line. The lines sit on different system boundaries
    and are deliberately NOT netted (ADR 0011); the figure shows them side by
    side, with biogenic storage plotted negative (sequestered). Returns the
    written ``Path``, or ``None`` if no ``summary.csv`` files exist.
    """
    path = Path(path)
    table = build_metric_table(path, CARBON_METRICS)
    if not table:
        return None

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_INCHES)
    group_width = 0.8
    bar_width = group_width / len(CARBON_METRICS)
    for metric_index, metric in enumerate(CARBON_METRICS):
        positions = [
            combo_index - group_width / 2 + (metric_index + 0.5) * bar_width
            for combo_index in range(len(table))
        ]
        scaled = [to_kilotonnes(row["values"][metric]) for row in table]
        means = [mean for mean, _, _ in scaled]
        err_low = [mean - low for mean, low, _ in scaled]
        err_high = [high - mean for mean, _, high in scaled]
        ax.bar(
            positions,
            means,
            width=bar_width,
            yerr=[err_low, err_high],
            capsize=2,
            error_kw={"elinewidth": 0.8},
            color=CARBON_METRIC_COLORS[metric],
            edgecolor="black",
            linewidth=0.5,
            label=CARBON_METRIC_LABELS[metric],
        )
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels([row["label"] for row in table], fontsize=8, rotation=20)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_ylabel("kt CO$_2$e (negative = sequestered)")
    ax.set_title("Three carbon lines per configuration (not netted)")
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    output_path = path / filename
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Bullwhip, residence, and carbon KPI-family figures (browser-free PDFs)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help="Scenario dir holding {combo}/summary.csv (default: the Baseline scenario).",
    )
    args = parser.parse_args()

    target = Path(args.path)
    written_paths = [
        producer(target)
        for producer in (
            write_bullwhip_figure,
            write_residence_figure,
            write_carbon_figure,
        )
    ]
    if all(written is None for written in written_paths):
        raise SystemExit(f"No summary.csv files found under {target}")
    for written in written_paths:
        print(f"Wrote {written}")
