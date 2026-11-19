"""Collector efficiency is the same for every policy and strategy (ADR 0025)."""
import itertools

import pytest
import simpy

from config.constants import COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY
from models.enums import InventoryPolicy, StockStrategy, WasteType
from tests.core.factories import make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
DAYS = 200


def _efficiency_after_aging(waste_monitor, policy, strategy, fill_fraction, signal_count):
    """A real collector with its center ``fill_fraction`` full and ``signal_count`` unserved signals."""
    env = simpy.Environment()
    collector = make_collector(env, waste_monitor, inventory_policy=policy, stock_strategy=strategy)
    collector.collection_center.current_storage[WASTE] = fill_fraction * collector.collection_center.waste_storage_capacity
    for index in range(signal_count):
        collector.kanban_manager.add_signal(
            waste_type=WASTE, timestamp=float(DAYS), volume=10.0,
            source_id=f"absent-generator-{index}", source_type="generator",
        )
    env.run(until=DAYS + 0.5)
    return collector.efficiency


@pytest.mark.parametrize("fill_fraction,signal_count", [(0.0, 0), (0.5, 3), (0.95, 10)])
def test_every_combo_gets_the_same_aging_only_efficiency(ledger_waste_monitor, fill_fraction, signal_count):
    """Mutation check (red): let utilization or signal count into ``update_efficiency``."""
    efficiencies = {
        (policy, strategy): _efficiency_after_aging(ledger_waste_monitor, policy, strategy, fill_fraction, signal_count)
        for policy, strategy in itertools.product(InventoryPolicy, StockStrategy)
    }

    expected = 1.0 - DAYS * COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY
    assert expected == pytest.approx(0.9)
    assert efficiencies == {combo: pytest.approx(expected) for combo in efficiencies}
