"""Stochastic dominance over the Monte Carlo run distribution of each KPI.

Comparing two configurations by their KPI *means* (with CIs) is a statement about
one summary number. Stochastic dominance is a stronger, distribution-level claim:
it asks whether one configuration's whole empirical distribution sits above the
other's, so that *every* decision maker of a given risk attitude would prefer it.

- First-order (FSD): ``F_A(x) <= F_B(x)`` for all ``x`` (A's CDF lies entirely at
  or below B's), so A is stochastically larger -- preferred by every decision
  maker with increasing utility, regardless of risk attitude.
- Second-order (SSD): the integrated-CDF condition ``integral F_A <= integral F_B``
  for all ``x`` -- preferred by every *risk-averse* (increasing, concave-utility)
  decision maker. FSD implies SSD, so the report names the strongest order that
  holds.

The dominance math here is sense-free: it is computed on the raw KPI values as
"which distribution is stochastically larger". Whether *larger* is *better* is the
per-KPI ``sense`` (service level: larger is better; emissions/landfill/cost:
larger is worse), carried as an annotation column so the artifact reports the
factual relation and its interpretation separately. KPIs without a documented
sense (the discovered ``bullwhip``/``residence`` namespaces) still get a factual
dominance direction with a blank sense.

This module imports NO project code, for the same reason as
``monitoring/paired_comparison.py`` and ``monitoring/pareto.py``: it must run as a
bare file (``python monitoring/stochastic_dominance.py <dir>``) where
``sys.path[0]`` is ``monitoring/`` and a ``monitoring.*`` / ``config.*`` import
would not resolve (and would trip the ``monitoring/__init__`` circular import).
The small run-file loader and namespace-flattening below are therefore duplicated
from ``paired_comparison.py`` rather than imported -- the same deliberate
duplication those two siblings already take. ``main.py`` imports
``write_dominance_report`` by module path, beside ``write_paired_comparison_report``.

On the Common Random Numbers (CRN) design: FSD and SSD are properties of the
*marginal* run distributions, which the seed pairing does not change, so this
module makes the distribution-level claim that *complements* the CRN-paired
mean-difference claim of ``paired_comparison.py`` rather than re-deriving it. It
reads the same CRN-paired ``run_*.json`` dataset; the pairing is exploited there,
not here.
"""

import json
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Curated headline KPIs compared by default, mirroring
# paired_comparison.DEFAULT_METRICS so the dominance artifact lines up one-to-one
# with the paired-mean artifact it complements.
DEFAULT_METRICS = [
    "service_level_full_pct",
    "service_level_operational_pct",
    "stockout_lost_m3",
    "total_consumed_m3",
    "landfill_volume_m3",
    "total_emissions_kgco2e",
    "overall_efficiency_pct",
    "collection_rate_pct",
]

# Per-KPI sense: "max" = larger is better, "min" = larger is worse. Used only to
# annotate the report (the dominance math is sense-free). Discovered namespace
# metrics are intentionally absent -- their sense is mixed (e.g. residence times
# fall vs throughput rises), so the report leaves their sense blank rather than
# assert a wrong one. Kept in-module rather than in config/constants.py for the
# same project-import-free reason as DEFAULT_METRICS.
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

# Relative tolerance for the second-order (integrated-CDF) comparison. The
# empirical CDF values are exact multiples of ``1/n`` so the first-order
# comparison needs no tolerance, but the integrated CDF multiplies them by
# floating interval widths, so its accumulation carries ~1e-13 rounding noise.
# The tolerance is scaled by the KPI's value range (the integrated CDF has the
# KPI's units), so it stays a fixed *relative* slack regardless of KPI magnitude.
SSD_RELATIVE_TOLERANCE = 1e-9

# Minimum replications per configuration to treat its KPI samples as a
# distribution. One value is a point mass, not a distribution to dominate.
MINIMUM_SAMPLES = 2

# Nested KPI namespaces extract_kpis emits as sub-dicts; lifted to flat
# ``{namespace}.{key}`` metrics. MUST mirror paired_comparison._GENERIC_NAMESPACES
# (duplicated, not imported, to keep this file bare-runnable).
_GENERIC_NAMESPACES = ("bullwhip", "residence")


def _flatten_namespaces(kpis: dict) -> dict:
    """Lift each nested generic namespace sub-dict to top-level ``{namespace}.{key}``.

    Duplicated from ``paired_comparison._flatten_namespaces`` (see module
    docstring). ``None`` values are preserved so the drop-on-``None`` sampling
    below fires identically on lifted keys.
    """
    flattened = {
        key: value for key, value in kpis.items() if key not in _GENERIC_NAMESPACES
    }
    for namespace in _GENERIC_NAMESPACES:
        nested = kpis.get(namespace)
        if not isinstance(nested, dict):
            continue
        for key, value in nested.items():
            flattened[f"{namespace}.{key}"] = value
    return flattened


def load_combo_kpis(scenario_dir: Path) -> Dict[str, Dict[int, dict]]:
    """Load per-run KPIs grouped by combo label, keyed by seed.

    Returns ``{combo_label: {seed: kpis_dict}}`` with ``combo_label`` read from
    each run file (``"{inventory_policy}__{stock_strategy}"``), not the directory
    name, so the grouping survives directory renames. Duplicated from
    ``paired_comparison.load_combo_kpis`` (see module docstring).
    """
    combos: Dict[str, Dict[int, dict]] = {}
    for run_path in sorted(scenario_dir.glob("*/run_*.json")):
        with open(run_path, "r", encoding="utf-8") as handle:
            run = json.load(handle)
        label = f"{run['inventory_policy']}__{run['stock_strategy']}"
        combos.setdefault(label, {})[run["seed"]] = _flatten_namespaces(run["kpis"])
    return combos


def _discovered_namespace_metrics(combos: Dict[str, Dict[int, dict]]) -> List[str]:
    """Insertion-ordered union of lifted ``{namespace}.*`` metric keys across runs.

    Mirrors ``paired_comparison._discovered_namespace_metrics`` so the dominance
    artifact lists the namespaced metrics in the same order as the paired one.
    """
    prefixes = tuple(f"{namespace}." for namespace in _GENERIC_NAMESPACES)
    discovered: Dict[str, None] = {}
    for runs in combos.values():
        for kpis in runs.values():
            for key in kpis:
                if key.startswith(prefixes):
                    discovered.setdefault(key, None)
    return list(discovered)


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

    A is stochastically larger (A FSD B) iff its empirical CDF lies entirely at or
    below B's -- ``F_A(x) <= F_B(x)`` for every ``x`` with strict inequality
    somewhere. The CDF difference is piecewise-constant, changing only at sample
    points, so evaluating on the sorted union of both samples checks every region
    exactly. ``F(x) = #{s <= x} / n`` is exact integer-over-``n`` arithmetic, so
    no floating tolerance is needed (and identical distributions, having no strict
    improvement, dominate in neither direction).
    """
    grid = sorted(set(samples_a) | set(samples_b))
    n_a, n_b = len(samples_a), len(samples_b)

    a_cdf_never_above = True  # F_A <= F_B everywhere  -> A is the larger one
    a_cdf_below_somewhere = False  # F_A < F_B somewhere -> strict for A
    b_cdf_never_above = True
    b_cdf_below_somewhere = False
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

    A second-order dominates B iff the integrated CDF of A stays at or below that
    of B -- ``integral_{-inf}^{x} F_A <= integral F_B`` for every ``x`` with strict
    inequality somewhere -- the condition every risk-averse increasing-utility
    decision maker uses. The integrated CDF of an empirical step function is
    piecewise-linear, so its difference is monotone between sample points and
    checking the running integral at each grid point is exact in the limit. The
    accumulation multiplies exact CDF values by floating interval widths, so a
    comparison is called a tie within ``relative_tolerance`` scaled by the KPI's
    value range (the integrated CDF carries the KPI's units).
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

    parser = argparse.ArgumentParser(
        description="Stochastic (FSD/SSD) dominance between policy/strategy combos "
        "over the Monte Carlo run distribution of each KPI."
    )
    parser.add_argument(
        "scenario_dir",
        nargs="?",
        default="outputs/baseline/Baseline",
        help="Directory holding {combo}/run_*.json files (default: outputs/baseline/Baseline)",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario_dir)
    report_rows = build_dominance_report(scenario_path)
    if not report_rows:
        raise SystemExit(f"No comparable run files under {scenario_path}")
    report = write_dominance_report(scenario_path)
    print(f"Wrote {report}")
    _print_dominance_summary(report_rows)
