"""A PULL operator short of local stock also signals the region holding the most (ADR 0033)."""
from types import SimpleNamespace

import simpy

from models.enums import InventoryPolicy, RegionType
from models.state import SimulationState
from tests.core.test_operating_clock import CONSTRUCTION, _treatment
from tests.core.test_treatment_outage_and_empty_collector import _fake_collector


def _generator(region, stock):
    return SimpleNamespace(region_type=region, waste_streams={CONSTRUCTION: SimpleNamespace(volume=stock)})


def _signals_after_order(local_generator_stock, needed_volume=100.0):
    env = simpy.Environment()
    state = SimulationState()
    operator = _treatment(env, inventory_policy=InventoryPolicy.PULL, state=state)
    small_region, large_region = [r for r in RegionType if r != operator.region_type][:2]
    local = _fake_collector(operator.region_type, {})
    small = _fake_collector(small_region, {})
    large = _fake_collector(large_region, {})
    state.collectors = [local, small, large]
    state.generators = [
        _generator(operator.region_type, local_generator_stock),
        _generator(small_region, 50.0),
        _generator(large_region, 400.0),
    ]

    operator._propagate_signal_to_collectors(CONSTRUCTION, needed_volume, 1.0)

    return {
        name: [signal["volume"] for signal in collector.kanban_manager.get_signals()]
        for name, collector in [("local", local), ("small", small), ("large", large)]
    }


def test_deficit_goes_to_the_region_with_the_largest_generator_stock():
    """Mutation check (red): drop the surplus-region signal."""
    assert _signals_after_order(local_generator_stock=30.0) == {"local": [100.0], "small": [], "large": [70.0]}


def test_no_remote_signal_when_local_stock_covers_the_order():
    """Mutation check (red): signal the surplus region regardless of local stock."""
    assert _signals_after_order(local_generator_stock=150.0) == {"local": [100.0], "small": [], "large": []}
