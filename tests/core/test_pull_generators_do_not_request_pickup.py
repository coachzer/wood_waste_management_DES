"""Under PULL only demand moves waste: a full generator does not call for pickup (ADR 0032)."""
from types import SimpleNamespace

import pytest

from core.generator import WasteGenerator
from core.kanban_manager import KanbanManager
from core.strategies.inventory_policy import build_inventory_policy
from core.strategies.stock_strategy import build_stock_strategy
from models.data_classes import WasteStream
from models.enums import InventoryPolicy, StockStrategy, WasteType

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05


def _full_generator(policy, strategy):
    generator = SimpleNamespace(
        name="gen_gorenjska",
        current_storage=1_000.0,
        waste_storage_capacity=1_000.0,
        waste_streams={SAWDUST: WasteStream(waste_type=SAWDUST, volume=1_000.0)},
        kanban_manager=KanbanManager(),
        inventory_policy_behavior=build_inventory_policy(policy),
        stock_strategy_behavior=build_stock_strategy(strategy),
    )
    generator._kanban_signal = lambda current_time: WasteGenerator._kanban_signal(generator, current_time)
    return generator


@pytest.mark.parametrize("strategy", list(StockStrategy))
def test_full_pull_generator_posts_nothing(strategy):
    """Mutation check (red): drop the policy gate in _handle_inventory_signaling."""
    generator = _full_generator(InventoryPolicy.PULL, strategy)

    WasteGenerator._handle_inventory_signaling(generator, current_time=5.0)

    assert generator.kanban_manager.get_signals(5.0) == []


@pytest.mark.parametrize("strategy", list(StockStrategy))
def test_full_push_generator_still_posts(strategy):
    generator = _full_generator(InventoryPolicy.PUSH, strategy)

    WasteGenerator._handle_inventory_signaling(generator, current_time=5.0)

    assert [signal["source_type"] for signal in generator.kanban_manager.get_signals(5.0)] == ["generator"]
