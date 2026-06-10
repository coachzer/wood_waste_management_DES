"""Shared KPI-namespace plumbing for the post-hoc analysis modules.

Single source of truth for the constants and run-loading helpers that
``baseline_aggregate``, ``paired_comparison``, and ``stochastic_dominance`` all
need. These were triplicated across the three modules back when each had to stay
import-free to run as a bare file (the old ``monitoring/__init__`` import cycle).
The clean-monitoring refactor killed that cycle, so the modules now run via
``python -m analysis.<module>`` and import this leaf instead of copying it.

This module is a leaf: it imports only the standard library and scipy, so
importing it can never reintroduce a project-internal cycle.
"""

import json
import math
from pathlib import Path
from typing import Dict, List

from scipy import stats


def t_ci_margin(n: int, stdev: float, alpha: float) -> float:
    """Two-sided Student-t CI half-width for a mean of ``n`` samples (ADR 0008).

    ``t.ppf(1 - alpha/2, n-1) * stdev / sqrt(n)`` -- the one formula behind both
    the marginal ``summary.csv`` CIs and the paired-difference CIs. Requires
    ``n > 1`` (zero degrees of freedom has no t quantile).
    """
    return float(stats.t.ppf(1 - alpha / 2, n - 1)) * stdev / math.sqrt(n)

# Curated headline KPIs compared by default in the paired and stochastic-dominance
# reports. Restricting the set keeps each metric's comparison family small (so the
# Holm correction stays powerful) and lines the two artifacts up one-to-one.
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

# Per-KPI sense: "max" = larger is better, "min" = larger is worse. The one
# encoding behind both the stochastic-dominance sense annotation and the Pareto
# objective vector (cleanup task #46); each report selects the keys it needs.
# Discovered namespace metrics are intentionally absent -- their sense is mixed.
KPI_SENSE: Dict[str, str] = {
    "service_level_full_pct": "max",
    "service_level_operational_pct": "max",
    "stockout_lost_m3": "min",
    "total_consumed_m3": "max",
    "landfill_volume_m3": "min",
    "total_emissions_kgco2e": "min",
    "overall_efficiency_pct": "max",
    "collection_rate_pct": "max",
    "total_system_cost": "min",
}

# Nested KPI sub-dicts ``extract_kpis`` emits, ridden generically as flat
# ``{namespace}.{key}`` metrics with no per-key wiring (issue 06). ``bullwhip``
# (ADR 0004), ``residence`` (Little's Law, C4), ``carbon`` (ADR 0011),
# ``availability`` (entity status history, cleanup task #61).
_GENERIC_NAMESPACES = ("bullwhip", "residence", "carbon", "availability")


def _flatten_namespaces(kpis: dict) -> dict:
    """Lift each nested generic namespace sub-dict to top-level
    ``{namespace}.{key}`` keys so downstream functions work on flat keys.

    Only the registered namespaces are flattened; other keys (including the nested
    ``service_level_full_by_product_pct`` dict) pass through untouched. ``None``
    values are preserved so the paired drop-on-``None`` semantics fire identically
    on lifted keys.
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

    Returns ``{combo_label: {seed: kpis_dict}}`` where ``combo_label`` is
    ``"{inventory_policy}__{stock_strategy}"`` read from each run file (not the
    directory name, so the grouping survives directory renames). The nested
    generic namespaces are flattened to ``{namespace}.{key}`` metrics on load.
    """
    combos: Dict[str, Dict[int, dict]] = {}
    for run_path in sorted(scenario_dir.glob("*/run_*.json")):
        with open(run_path, "r", encoding="utf-8") as f:
            run = json.load(f)
        label = f"{run['inventory_policy']}__{run['stock_strategy']}"
        combos.setdefault(label, {})[run["seed"]] = _flatten_namespaces(run["kpis"])
    return combos


def _discovered_namespace_metrics(combos: Dict[str, Dict[int, dict]]) -> List[str]:
    """Insertion-ordered union of lifted ``{namespace}.*`` metric keys across runs.

    Mirrors issue 06's discovery: keys surface in the order ``extract_kpis``
    authors them, so ``summary.csv``, ``paired_comparison.csv``, and
    ``stochastic_dominance.csv`` list the namespaced metrics identically.
    Discovery is a union -- a run missing a key still contributes the keys it has.
    """
    prefixes = tuple(f"{namespace}." for namespace in _GENERIC_NAMESPACES)
    discovered: Dict[str, None] = {}
    for runs in combos.values():
        for kpis in runs.values():
            for key in kpis:
                if key.startswith(prefixes):
                    discovered.setdefault(key, None)
    return list(discovered)
