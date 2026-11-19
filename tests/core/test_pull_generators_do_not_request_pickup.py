"""Under PULL only demand moves waste: a full generator does not call for pickup (ADR 0032)."""
import pytest
import simpy

from models.enums import InventoryPolicy, StockStrategy, WasteType
from tests.core.factories import make_waste_generator

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05


def _signals_after_one_tick_full(waste_monitor, policy, strategy):
    """A real generator starting at full storage runs its t=0 tick; returns the signals it posted."""
    env = simpy.Environment()
    generator = make_waste_generator(
        env, waste_monitor, {SAWDUST: 0.0},
        waste_storage_capacity=1_000.0, initial_stock={SAWDUST: 1_000.0},
        inventory_policy=policy, stock_strategy=strategy,
    )
    env.run(until=0.5)
    return generator.kanban_manager.get_signals(0.0)


@pytest.mark.parametrize("strategy", list(StockStrategy))
def test_full_pull_generator_posts_nothing(ledger_waste_monitor, strategy):
    """Mutation check (red): drop the policy gate in _handle_inventory_signaling."""
    assert _signals_after_one_tick_full(ledger_waste_monitor, InventoryPolicy.PULL, strategy) == []


@pytest.mark.parametrize("strategy", list(StockStrategy))
def test_full_push_generator_still_posts(ledger_waste_monitor, strategy):
    signals = _signals_after_one_tick_full(ledger_waste_monitor, InventoryPolicy.PUSH, strategy)

    assert [(signal["source_type"], signal["volume"]) for signal in signals] == [("generator", 1_000.0)]
