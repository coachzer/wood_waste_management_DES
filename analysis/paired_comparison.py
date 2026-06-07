"""Paired comparison of policy/strategy combinations under common random numbers.

The baseline Monte Carlo reuses the same seed series (``base_seed + i``) across
every InventoryPolicy x StockStrategy combo, so replication ``i`` of two combos
faces identical draws -- Common Random Numbers (CRN; see CLAUDE.md "Seeding").
``summary.csv`` reports only marginal per-combo CIs, which do not exploit the
pairing. This module reports the paired version: per-replication KPI
**differences** paired by seed, a paired-t CI on the mean difference, and a
Holm-Bonferroni correction across each metric's family of pairwise comparisons.
It consumes the persisted ``run_*.json`` files, so it runs post-hoc without
re-simulating.
"""

import math
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy import stats

from ._kpi_shared import (
    DEFAULT_METRICS,
    _discovered_namespace_metrics,
    load_combo_kpis,
)


def paired_differences(
    kpis_a: Dict[int, dict], kpis_b: Dict[int, dict], metric: str
) -> List[float]:
    """Per-seed differences ``A - B`` for a metric, over seeds present in both.

    Seeds missing the metric (``None``) in either combo are dropped so the
    comparison stays genuinely paired.
    """
    shared_seeds = sorted(set(kpis_a) & set(kpis_b))
    diffs = []
    for seed in shared_seeds:
        value_a = kpis_a[seed].get(metric)
        value_b = kpis_b[seed].get(metric)
        if value_a is None or value_b is None:
            continue
        diffs.append(float(value_a) - float(value_b))
    return diffs


def paired_t_comparison(diffs: List[float], alpha: float = 0.05) -> Optional[dict]:
    """Paired-t summary of a difference sample: mean, sd, CI, t, two-sided p.

    Returns ``None`` for fewer than two pairs (a CI is undefined). A
    zero-variance sample (every replication produced an identical difference,
    e.g. a structurally constant KPI) is handled explicitly: a constant nonzero
    difference is deterministically significant, a constant zero difference is
    not.
    """
    n = len(diffs)
    if n < 2:
        return None

    diffs_array = np.asarray(diffs, dtype=float)
    mean_diff = float(diffs_array.mean())
    sd_diff = float(diffs_array.std(ddof=1))
    standard_error = sd_diff / math.sqrt(n)

    if standard_error == 0.0:
        return {
            "n_pairs": n,
            "mean_diff": mean_diff,
            "sd_diff": 0.0,
            "ci_low": mean_diff,
            "ci_high": mean_diff,
            "t_stat": float("inf") if mean_diff != 0.0 else 0.0,
            "p_value": 0.0 if mean_diff != 0.0 else 1.0,
        }

    t_critical = float(stats.t.ppf(1 - alpha / 2, n - 1))
    margin = t_critical * standard_error
    t_stat = mean_diff / standard_error
    p_value = float(2 * stats.t.sf(abs(t_stat), n - 1))
    return {
        "n_pairs": n,
        "mean_diff": mean_diff,
        "sd_diff": sd_diff,
        "ci_low": mean_diff - margin,
        "ci_high": mean_diff + margin,
        "t_stat": t_stat,
        "p_value": p_value,
    }


def holm_adjusted(p_values: List[float]) -> List[float]:
    """Holm-Bonferroni step-down adjusted p-values, in the input order.

    Holm controls the family-wise error rate and is uniformly more powerful
    than plain Bonferroni. A comparison is significant at level ``alpha`` when
    its adjusted p-value is ``<= alpha``.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, index in enumerate(order):
        candidate = min((m - rank) * p_values[index], 1.0)
        running_max = max(running_max, candidate)
        adjusted[index] = running_max
    return adjusted


def build_paired_report(
    scenario_dir: Path,
    metrics: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> List[dict]:
    """Compute every pairwise paired comparison for the requested metrics.

    The Holm correction is applied *per metric* (the family is the set of
    combo-pair comparisons for that one metric), so the family-wise error rate
    is controlled at ``alpha`` for each metric's question independently.

    When ``metrics`` is left at its default, the discovered ``bullwhip.*`` keys
    are appended after the curated set so the namespace flows through without
    wiring (issue 07). An explicit ``metrics`` list is honored verbatim.
    """
    combos = load_combo_kpis(scenario_dir)
    if metrics is None:
        metrics = DEFAULT_METRICS + _discovered_namespace_metrics(combos)
    combo_labels = sorted(combos)

    rows: List[dict] = []
    for metric in metrics:
        family: List[dict] = []
        for label_a, label_b in combinations(combo_labels, 2):
            diffs = paired_differences(combos[label_a], combos[label_b], metric)
            comparison = paired_t_comparison(diffs, alpha=alpha)
            if comparison is None:
                continue
            family.append({"metric": metric, "combo_a": label_a, "combo_b": label_b, **comparison})

        if not family:
            continue
        adjusted = holm_adjusted([row["p_value"] for row in family])
        for row, p_adjusted in zip(family, adjusted):
            row["p_value_holm"] = p_adjusted
            row["significant_holm"] = p_adjusted <= alpha
        rows.extend(family)
    return rows


def write_paired_comparison_report(
    scenario_dir: Path,
    metrics: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> Optional[Path]:
    """Write ``paired_comparison.csv`` for a scenario and return its path.

    Returns ``None`` when there is nothing to compare (no run files, or every
    combo has fewer than two shared replications).
    """
    rows = build_paired_report(scenario_dir, metrics=metrics, alpha=alpha)
    if not rows:
        return None

    header = [
        "metric", "combo_a", "combo_b", "n_pairs", "mean_diff", "sd_diff",
        "ci95_low", "ci95_high", "t_stat", "p_value", "p_value_holm", "significant_holm",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(
            f"{row['metric']},{row['combo_a']},{row['combo_b']},{row['n_pairs']},"
            f"{row['mean_diff']:.6g},{row['sd_diff']:.6g},{row['ci_low']:.6g},{row['ci_high']:.6g},"
            f"{row['t_stat']:.6g},{row['p_value']:.6g},{row['p_value_holm']:.6g},{row['significant_holm']}"
        )

    report_path = scenario_dir / "paired_comparison.csv"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _print_significant_summary(rows: List[dict], alpha: float) -> None:
    """Console digest: the Holm-significant pairs, grouped by metric."""
    significant = [row for row in rows if row.get("significant_holm")]
    if not significant:
        print(f"No pairwise differences significant after Holm correction (alpha={alpha}).")
        return
    print(f"Holm-significant pairwise differences (alpha={alpha}):")
    current_metric = None
    for row in significant:
        if row["metric"] != current_metric:
            current_metric = row["metric"]
            print(f"\n  {current_metric}:")
        direction = ">" if row["mean_diff"] > 0 else "<"
        print(
            f"    {row['combo_a']} {direction} {row['combo_b']}  "
            f"(diff={row['mean_diff']:.4g}, 95% CI [{row['ci_low']:.4g}, {row['ci_high']:.4g}], "
            f"p_holm={row['p_value_holm']:.3g}, n={row['n_pairs']})"
        )


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Paired (CRN) comparison of policy/strategy combos from baseline run files."
    )
    parser.add_argument(
        "scenario_dir",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help=f"Directory holding {{combo}}/run_*.json files (default: {BASELINE_SCENARIO_DEFAULT})",
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="Family-wise significance level")
    args = parser.parse_args()

    scenario_path = Path(args.scenario_dir)
    rows = build_paired_report(scenario_path, alpha=args.alpha)
    if not rows:
        raise SystemExit(f"No comparable run files under {scenario_path}")
    report = write_paired_comparison_report(scenario_path, alpha=args.alpha)
    print(f"Wrote {report}")
    _print_significant_summary(rows, args.alpha)
