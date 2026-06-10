"""Shared factory fixtures for the monitoring test suite.

Each fixture returns a builder function that was previously duplicated across
test modules. They are factories (fixtures returning callables) so the tests
keep their inline call-with-arguments style unchanged.
"""

import json

import pytest


@pytest.fixture
def write_run():
    """Persist one ``run_*.json`` the way the baseline run does, under its combo dir."""

    def _write_run(scenario_dir, inventory_policy, stock_strategy, seed, kpis):
        combo_dir = scenario_dir / f"{inventory_policy}__{stock_strategy}"
        combo_dir.mkdir(parents=True, exist_ok=True)
        run = {
            "inventory_policy": inventory_policy,
            "stock_strategy": stock_strategy,
            "seed": seed,
            "kpis": kpis,
        }
        (combo_dir / f"run_{seed:03d}.json").write_text(json.dumps(run), encoding="utf-8")

    return _write_run


@pytest.fixture
def write_summary():
    """Write a minimal summary.csv (the real header + a row per metric)."""

    def _write_summary(combo_dir, means):
        combo_dir.mkdir(parents=True, exist_ok=True)
        lines = ["metric,mean,stdev,ci95_low,ci95_high,count"]
        for metric, mean in means.items():
            lines.append(f"{metric},{mean},0,0,0,10")
        (combo_dir / "summary.csv").write_text("\n".join(lines), encoding="utf-8")

    return _write_summary


@pytest.fixture
def monitor_data():
    """Build a monitor_data carrying only products.by_type series per operator.

    ``per_operator`` is a list of ``{product: [cumulative series]}`` dicts, one
    per treatment operator.
    """

    def _monitor_data(per_operator):
        return {
            "processing_history": {
                f"op{i}": {"products": {"by_type": by_type}}
                for i, by_type in enumerate(per_operator)
            }
        }

    return _monitor_data
