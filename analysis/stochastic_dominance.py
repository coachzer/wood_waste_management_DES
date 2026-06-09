"""Stochastic dominance over the Monte-Carlo run distribution of each KPI.

A distribution-level comparison stronger than comparing means: it asks whether
one configuration's whole empirical CDF sits above the other's. First-order (FSD)
and second-order (SSD) are defined in the **Stochastic Dominance** glossary term
(CONTEXT.md); the report names the strongest order that holds and carries the
per-KPI *sense* as a separate annotation (the dominance math is sense-free, so
KPIs without a documented sense still get a factual direction with a blank
sense). It reads the same CRN-paired ``run_*.json`` set as
``paired_comparison.py`` and complements its mean-difference claim -- FSD/SSD are
properties of the marginal distributions, which seed pairing does not change.

It reads the run-file loader, namespace flattening, and ``DEFAULT_METRICS`` from
``analysis._kpi_shared`` (the single source of truth shared with
``paired_comparison.py`` and ``baseline_aggregate.py``), and runs via
``python -m analysis.stochastic_dominance <dir>``.
"""

from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ._kpi_shared import (
    DEFAULT_METRICS,
    _discovered_namespace_metrics,
    load_combo_kpis,
)

# Per-KPI sense: "max" = larger is better, "min" = larger is worse. Annotation
# only (the dominance math is sense-free). Discovered namespace metrics are
# intentionally absent -- their sense is mixed, so the report leaves it blank.
# In-module rather than in constants.py: this is dominance-report presentation,
# not a project-wide constant.
KPI_SENSES: Dict[str, str] = {
    "service_level_full_pct": "max",
    "service_level_operational_pct": "max",
    "stockout_lost_m3": "min",
    "total_consumed_m3": "max",
    "landfill_volume_m3": "min",
    "total_emissions_kgco2e": "min",
    "overall_efficiency_pct": "max",
    "collection_rate_pct": "max",
}

# Relative tolerance for the second-order (integrated-CDF) comparison: its
# accumulation carries ~1e-13 floating rounding noise (the first-order comparison
# is exact multiples of 1/n and needs none). Scaled by the KPI's value range so
# it stays a fixed relative slack regardless of magnitude.
SSD_RELATIVE_TOLERANCE = 1e-9

# Minimum replications per configuration to treat its KPI samples as a
# distribution. One value is a point mass, not a distribution to dominate.
MINIMUM_SAMPLES = 2


def _metric_samples(runs: Dict[int, dict], metric: str) -> List[float]:
    """KPI values for a metric across a combo's runs, dropping missing ones.

    Seeds where the metric is absent or ``None`` are dropped, so a partially
    populated KPI still yields a distribution over the seeds that have it.
    """
    samples = []
    for kpis in runs.values():
        value = kpis.get(metric)
        if value is None:
            continue
        samples.append(float(value))
    return samples


def first_order_dominance(
    samples_a: List[float], samples_b: List[float]
) -> Optional[str]:
    """Return ``"a"`` if A FSD B, ``"b"`` if B FSD A, else ``None``.

    A FSD B iff ``F_A(x) <= F_B(x)`` for every ``x`` with strict inequality
    somewhere (see the **Stochastic Dominance** glossary term). The CDF difference
    changes only at sample points, so evaluating on the sorted union of both
    samples is exact; ``F(x) = #{s <= x} / n`` is exact integer-over-``n``
    arithmetic, so no floating tolerance is needed and identical distributions
    dominate in neither direction.
    """
    grid = sorted(set(samples_a) | set(samples_b))
    n_a, n_b = len(samples_a), len(samples_b)

    a_cdf_never_above = True  # F_A <= F_B everywhere  -> A is the larger one
    a_cdf_below_somewhere = False  # F_A < F_B somewhere -> strict for A
    b_cdf_never_above = True
    for x in grid:
        cdf_a = sum(1 for sample in samples_a if sample <= x) / n_a
        cdf_b = sum(1 for sample in samples_b if sample <= x) / n_b
        if cdf_a > cdf_b:
            a_cdf_never_above = False
        elif cdf_a < cdf_b:
            a_cdf_below_somewhere = True
            b_cdf_never_above = False
    # b_cdf_below_somewhere is exactly "F_A above somewhere", i.e. not a_never_above.
    b_cdf_below_somewhere = not a_cdf_never_above

    if a_cdf_never_above and a_cdf_below_somewhere:
        return "a"
    if b_cdf_never_above and b_cdf_below_somewhere:
        return "b"
    return None


def second_order_dominance(
    samples_a: List[float],
    samples_b: List[float],
    relative_tolerance: float = SSD_RELATIVE_TOLERANCE,
) -> Optional[str]:
    """Return ``"a"`` if A SSD B, ``"b"`` if B SSD A, else ``None``.

    A SSD B iff the integrated CDF of A stays at or below B's --
    ``integral_{-inf}^{x} F_A <= integral F_B`` for every ``x`` with strict
    inequality somewhere (see the **Stochastic Dominance** glossary term). The
    integrated CDF of an empirical step function is piecewise-linear, so checking
    the running integral at each grid point is exact; the accumulation carries
    floating noise, so ties are called within ``relative_tolerance`` scaled by the
    KPI's value range.
    """
    grid = sorted(set(samples_a) | set(samples_b))
    n_a, n_b = len(samples_a), len(samples_b)
    tolerance = relative_tolerance * (grid[-1] - grid[0]) if len(grid) > 1 else 0.0

    integral_a = 0.0
    integral_b = 0.0
    a_integral_never_above = True  # integral F_A <= integral F_B everywhere -> A larger
    a_integral_below_somewhere = False
    b_integral_never_above = True
    b_integral_below_somewhere = False
    previous = grid[0]
    for x in grid:
        width = x - previous
        # F is right-continuous: on [previous, x) it equals the CDF at `previous`.
        cdf_a_left = sum(1 for sample in samples_a if sample <= previous) / n_a
        cdf_b_left = sum(1 for sample in samples_b if sample <= previous) / n_b
        integral_a += cdf_a_left * width
        integral_b += cdf_b_left * width
        difference = integral_a - integral_b  # integral F_A - integral F_B
        if difference > tolerance:
            a_integral_never_above = False
        elif difference < -tolerance:
            a_integral_below_somewhere = True
        if -difference > tolerance:
            b_integral_never_above = False
        elif -difference < -tolerance:
            b_integral_below_somewhere = True
        previous = x

    if a_integral_never_above and a_integral_below_somewhere:
        return "a"
    if b_integral_never_above and b_integral_below_somewhere:
        return "b"
    return None


def dominance_relation(
    samples_a: List[float],
    samples_b: List[float],
    relative_tolerance: float = SSD_RELATIVE_TOLERANCE,
) -> Tuple[str, Optional[str]]:
    """Strongest dominance order between two samples and its winner.

    Returns ``(order, winner)`` where ``order`` is ``"FSD"``, ``"SSD"`` or
    ``"none"`` and ``winner`` is ``"a"``, ``"b"`` or ``None``. First-order is
    reported when it holds (it implies second-order), so the order names the
    strongest claim available.
    """
    first = first_order_dominance(samples_a, samples_b)
    if first is not None:
        return "FSD", first
    second = second_order_dominance(samples_a, samples_b, relative_tolerance)
    if second is not None:
        return "SSD", second
    return "none", None


def build_dominance_report(
    scenario_dir: Path,
    metrics: Optional[List[str]] = None,
    relative_tolerance: float = SSD_RELATIVE_TOLERANCE,
) -> List[dict]:
    """One row per (metric, combo-pair): the dominance order, winner and sense.

    For each metric and each unordered combo pair, the stronger-order dominance is
    computed over the two marginal run distributions. ``dominant_combo`` is the
    stochastically-larger combo's label (empty when neither dominates), and
    ``sense`` annotates whether larger is better (``"max"``), worse (``"min"``) or
    undocumented (``""``). Pairs where either combo has fewer than
    ``MINIMUM_SAMPLES`` values for the metric are skipped. Returns an empty list
    when no run files are found. Rows are ordered by metric, then combo pair.
    """
    combos = load_combo_kpis(scenario_dir)
    if not combos:
        return []
    if metrics is None:
        metrics = DEFAULT_METRICS + _discovered_namespace_metrics(combos)
    combo_labels = sorted(combos)

    rows: List[dict] = []
    for metric in metrics:
        for label_a, label_b in combinations(combo_labels, 2):
            samples_a = _metric_samples(combos[label_a], metric)
            samples_b = _metric_samples(combos[label_b], metric)
            if len(samples_a) < MINIMUM_SAMPLES or len(samples_b) < MINIMUM_SAMPLES:
                continue
            order, winner = dominance_relation(
                samples_a, samples_b, relative_tolerance
            )
            dominant_combo = (
                label_a if winner == "a" else label_b if winner == "b" else ""
            )
            rows.append(
                {
                    "metric": metric,
                    "combo_a": label_a,
                    "combo_b": label_b,
                    "n_a": len(samples_a),
                    "n_b": len(samples_b),
                    "dominance_order": order,
                    "dominant_combo": dominant_combo,
                    "sense": KPI_SENSES.get(metric, ""),
                }
            )
    return rows


def write_dominance_report(
    scenario_dir,
    metrics: Optional[List[str]] = None,
    relative_tolerance: float = SSD_RELATIVE_TOLERANCE,
) -> Optional[Path]:
    """Write ``stochastic_dominance.csv`` for a scenario and return its path.

    Returns ``None`` when there is nothing to compare (no run files, or no pair
    has enough samples for any metric). Lives beside ``paired_comparison.csv``.
    """
    scenario_dir = Path(scenario_dir)
    rows = build_dominance_report(
        scenario_dir, metrics=metrics, relative_tolerance=relative_tolerance
    )
    if not rows:
        return None

    header = [
        "metric", "combo_a", "combo_b", "n_a", "n_b",
        "dominance_order", "dominant_combo", "sense",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(
            f"{row['metric']},{row['combo_a']},{row['combo_b']},"
            f"{row['n_a']},{row['n_b']},{row['dominance_order']},"
            f"{row['dominant_combo']},{row['sense']}"
        )

    report_path = scenario_dir / "stochastic_dominance.csv"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _print_dominance_summary(rows: List[dict]) -> None:
    """Console digest: the FSD/SSD dominances, grouped by metric."""
    dominances = [row for row in rows if row["dominance_order"] != "none"]
    if not dominances:
        print("No stochastic dominance (FSD or SSD) found between any combo pair.")
        return
    print("Stochastic dominances (strongest order per pair):")
    current_metric = None
    for row in dominances:
        if row["metric"] != current_metric:
            current_metric = row["metric"]
            sense = KPI_SENSES.get(current_metric, "")
            sense_note = f" [larger is {'better' if sense == 'max' else 'worse'}]" if sense else ""
            print(f"\n  {current_metric}{sense_note}:")
        loser = row["combo_b"] if row["dominant_combo"] == row["combo_a"] else row["combo_a"]
        better = ""
        if row["sense"]:
            better = " (better)" if row["sense"] == "max" else " (worse)"
        print(
            f"    {row['dominant_combo']} {row['dominance_order']}-dominates {loser}"
            f"  larger{better}; n={row['n_a']}/{row['n_b']}"
        )


if __name__ == "__main__":
    import argparse

    from config.constants import BASELINE_SCENARIO_DEFAULT

    parser = argparse.ArgumentParser(
        description="Stochastic (FSD/SSD) dominance between policy/strategy combos "
        "over the Monte Carlo run distribution of each KPI."
    )
    parser.add_argument(
        "scenario_dir",
        nargs="?",
        default=BASELINE_SCENARIO_DEFAULT,
        help=f"Directory holding {{combo}}/run_*.json files (default: {BASELINE_SCENARIO_DEFAULT})",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario_dir)
    report_rows = build_dominance_report(scenario_path)
    if not report_rows:
        raise SystemExit(f"No comparable run files under {scenario_path}")
    report = write_dominance_report(scenario_path)
    print(f"Wrote {report}")
    _print_dominance_summary(report_rows)
