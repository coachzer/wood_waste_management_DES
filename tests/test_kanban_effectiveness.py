"""Test whether the kanban signal cascade has any measurable effect on PULL KPIs.

Runs PULL x ON_DEMAND with kanban enabled (default) vs. disabled (monkey-patched)
across several seeds and compares key KPIs. If they're identical, the kanban
upstream cascade is dead weight.
"""

import unittest
from unittest.mock import patch
from analysis.baseline_aggregate import extract_kpis
from main import run_single_simulation
from models.enums import InventoryPolicy, StockStrategy


SEEDS = [42, 43, 44]
SCENARIO = "Baseline"
POLICY = InventoryPolicy.PULL
STRATEGY = StockStrategy.ON_DEMAND

KPIS_TO_COMPARE = [
    "service_level_full_pct",
    "service_level_operational_pct",
    "total_processed_m3",
    "total_collected_m3",
    "landfill_volume_m3",
    "total_system_cost",
    "total_emissions_kgco2e",
    "collection_transport_cost",
]


def _run_and_extract(seed, disable_kanban=False):
    """Run one replication, optionally disabling kanban signals."""
    patches = []
    if disable_kanban:
        patches.append(patch(
            "core.strategies.inventory_policy.PullPolicy.propagates_reorder_signals_upstream",
            return_value=False,
        ))
        patches.append(patch(
            "core.strategies.inventory_policy.PullPolicy.should_process_kanban_signals",
            return_value=False,
        ))

    for p in patches:
        p.start()
    try:
        result = run_single_simulation(
            scenario_name=SCENARIO,
            inventory_policy=POLICY,
            stock_strategy=STRATEGY,
            seed=seed,
            create_mfa=False,
            raise_on_violation=False,
        )
    finally:
        for p in patches:
            p.stop()

    return extract_kpis(result["monitor_data"])


class TestKanbanEffectiveness(unittest.TestCase):
    """Compare PULL runs with and without kanban signal cascade."""

    def test_kanban_changes_kpis(self):
        diffs = []
        for seed in SEEDS:
            enabled = _run_and_extract(seed, disable_kanban=False)
            disabled = _run_and_extract(seed, disable_kanban=True)
            diffs.extend(_compare_kpis(seed, enabled, disabled))

        if not any(d["diff"] > 1e-9 for d in diffs):
            self.fail(
                "Kanban signal cascade had ZERO effect on any KPI across all seeds. "
                "The mechanism may be dead code."
            )


def _format_val(v):
    return f"{v:>12.4f}" if v is not None else "        None"


def _compare_kpis(seed, enabled, disabled):
    print(f"\n--- Seed {seed} ---")
    results = []
    for kpi in KPIS_TO_COMPARE:
        val_on = enabled.get(kpi)
        val_off = disabled.get(kpi)
        diff = abs(val_on - val_off) if val_on is not None and val_off is not None else 0.0
        marker = " <<<" if diff > 1e-9 else ""
        print(f"  {kpi:40s}  enabled={_format_val(val_on)}  disabled={_format_val(val_off)}  diff={diff:.6f}{marker}")
        results.append({"kpi": kpi, "diff": diff})
    return results


if __name__ == "__main__":
    unittest.main()
