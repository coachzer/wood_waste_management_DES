"""Strategy/policy behavior objects (arch-05 strategy extraction).

These cover the pluggable ``StockStrategy``/``InventoryPolicy`` behavior classes
that replaced the ``match self.stock_strategy`` / ``if self.inventory_policy ==``
branches in the process modules. These tests pin two things:

1. The factories map every enum selector to the class with that behavior.
2. PUSH paths never consult the signal callables, so PUSH ignores signals.
"""

import pytest

from config.constants import COLLECTOR_UTILIZATION_CEILING

from core.strategies import (
    OnDemandStrategy,
    Reorder50Strategy,
    Reorder90Strategy,
    PushPolicy,
    PullPolicy,
    build_stock_strategy,
    build_inventory_policy,
)
from models.enums import InventoryPolicy, StockStrategy


def _boom():
    """A callable that fails if invoked -- proves a lazy path stayed lazy."""
    raise AssertionError("signal callable must not be consulted on this path")


def test_factories_map_every_selector_to_its_behavior():
    assert {
        member: (
            build_stock_strategy(member).treatment_should_reorder(60.0, 100.0),
            build_stock_strategy(member).treatment_should_reorder(95.0, 100.0),
        )
        for member in StockStrategy
    } == {
        StockStrategy.ON_DEMAND: (True, True),
        StockStrategy.REORDER_50: (False, False),
        StockStrategy.REORDER_90: (True, False),
    }
    assert {
        member: build_inventory_policy(member).treatment_is_demand_driven()
        for member in InventoryPolicy
    } == {
        InventoryPolicy.PUSH: False,
        InventoryPolicy.PULL: True,
    }


# --- stock strategy thresholds --------------------------------------------

def test_reorder_adaptive_threshold_is_the_fraction():
    assert build_stock_strategy(StockStrategy.REORDER_50).collector_adaptive_threshold(999.0) == 0.5
    assert build_stock_strategy(StockStrategy.REORDER_90).collector_adaptive_threshold(999.0) == 0.9


def test_ondemand_adaptive_threshold_grows_with_time_and_caps():
    strategy = build_stock_strategy(StockStrategy.ON_DEMAND)
    assert strategy.collector_adaptive_threshold(0.0) == pytest.approx(0.10)
    assert strategy.collector_adaptive_threshold(100.0) == pytest.approx(0.20)
    # Time factor caps at 0.30, so the threshold caps at 0.40.
    assert strategy.collector_adaptive_threshold(10_000.0) == pytest.approx(0.40)


@pytest.mark.parametrize(
    "strategy, capacity, below, at",
    [
        (Reorder50Strategy(), 100.0, 49.9, 50.0),
        (Reorder90Strategy(), 100.0, 89.9, 90.0),
    ],
)
def test_reorder_treatment_trigger_fires_below_fraction(strategy, capacity, below, at):
    assert strategy.treatment_should_reorder(below, capacity) is True
    assert strategy.treatment_should_reorder(at, capacity) is False


def test_ondemand_treatment_trigger_fires_until_full():
    strategy = OnDemandStrategy()
    assert strategy.treatment_should_reorder(99.0, 100.0) is True
    assert strategy.treatment_should_reorder(100.0, 100.0) is False


# --- generator signaling (double dispatch + laziness) ----------------------

def test_reorder_generator_signal_ignores_policy():
    assert Reorder90Strategy().generator_should_signal(
        90.0, 100.0, PullPolicy()
    ) is True
    assert Reorder50Strategy().generator_should_signal(
        49.0, 100.0, PullPolicy()
    ) is False


def test_ondemand_generator_signal_push_uses_storage_threshold():
    strategy = OnDemandStrategy()
    assert strategy.generator_should_signal(11.0, 100.0, PushPolicy()) is True
    assert strategy.generator_should_signal(10.0, 100.0, PushPolicy()) is False


# --- inventory policy ------------------------------------------------------

def test_should_process_kanban_signals_is_pull_only():
    assert PushPolicy().should_process_kanban_signals(["s"]) is False
    assert PullPolicy().should_process_kanban_signals(["s"]) is True
    assert PullPolicy().should_process_kanban_signals([]) is False


def test_push_should_collect_uses_buffered_threshold_without_signals():
    # PUSH threshold = min(0.80, adaptive + 0.10); signals are never read.
    policy = PushPolicy()
    assert policy.collector_should_collect(0.55, 0.50, _boom) is True
    assert policy.collector_should_collect(0.65, 0.50, _boom) is False


def test_pull_collects_only_against_signals():
    # Kanban: no signal, no movement (ADR 0025). An empty collection center
    # with no signal must still stay idle.
    policy = PullPolicy()
    assert policy.collector_should_collect(0.70, 0.50, lambda: ["s"]) is True
    assert policy.collector_should_collect(0.0, 0.50, lambda: []) is False


def test_pull_signals_do_not_force_collection_at_the_utilization_ceiling():
    policy = PullPolicy()
    ceiling = COLLECTOR_UTILIZATION_CEILING
    assert policy.collector_should_collect(ceiling - 0.01, 0.50, lambda: ["s"]) is True
    assert policy.collector_should_collect(ceiling, 0.50, lambda: ["s"]) is False
    assert policy.collector_should_collect(0.99, 0.50, lambda: ["s"]) is False


def test_policy_production_and_signal_propagation_flags():
    assert PushPolicy().propagates_reorder_signals_upstream() is False
    assert PullPolicy().propagates_reorder_signals_upstream() is True
    assert PushPolicy().treatment_is_demand_driven() is False
    assert PullPolicy().treatment_is_demand_driven() is True
