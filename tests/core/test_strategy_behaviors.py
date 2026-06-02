"""Strategy/policy behavior objects (arch-05 strategy extraction).

These cover the pluggable ``StockStrategy``/``InventoryPolicy`` behavior classes
that replaced the ``match self.stock_strategy`` / ``if self.inventory_policy ==``
branches in the process modules. The byte-identical baseline run is the real
oracle for behavior preservation; these tests pin two things that run does not
make obvious:

1. The factories map every enum selector to the right concrete class (so adding
   a strategy is one class plus one mapping entry, zero process-module edits).
2. The lazy ``get_signals`` callables only fire on the exact paths the original
   inlined code consulted them -- ``get_signals`` prunes stale signals as a side
   effect, so an over-eager call would silently break reproducibility.
"""

import pytest

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


class _RecordingRng:
    """Stand-in numpy-style rng recording whether the jitter draw happened."""

    def __init__(self):
        self.calls = 0

    def uniform(self, low, high):
        self.calls += 1
        return 2.5  # arbitrary fixed jitter


# --- factories -------------------------------------------------------------

def test_build_stock_strategy_maps_every_enum():
    assert isinstance(build_stock_strategy(StockStrategy.ON_DEMAND), OnDemandStrategy)
    assert isinstance(build_stock_strategy(StockStrategy.REORDER_50), Reorder50Strategy)
    assert isinstance(build_stock_strategy(StockStrategy.REORDER_90), Reorder90Strategy)


def test_build_inventory_policy_maps_every_enum():
    assert isinstance(build_inventory_policy(InventoryPolicy.PUSH), PushPolicy)
    assert isinstance(build_inventory_policy(InventoryPolicy.PULL), PullPolicy)


# --- stock strategy thresholds --------------------------------------------

def test_reorder_adaptive_threshold_is_the_fraction():
    assert Reorder50Strategy().collector_adaptive_threshold(999.0) == 0.5
    assert Reorder90Strategy().collector_adaptive_threshold(999.0) == 0.9


def test_ondemand_adaptive_threshold_grows_with_time_and_caps():
    strategy = OnDemandStrategy()
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

def test_reorder_generator_signal_ignores_policy_and_signals():
    # Reorder strategies decide purely on storage vs fraction; the signal
    # callable must never be touched (the original never read it here).
    assert Reorder90Strategy().generator_should_signal(
        90.0, 100.0, PullPolicy(), _boom
    ) is True
    assert Reorder50Strategy().generator_should_signal(
        49.0, 100.0, PullPolicy(), _boom
    ) is False


def test_ondemand_generator_signal_push_uses_storage_threshold():
    # PUSH ON_DEMAND signals on substantial waste (> 10% capacity) and never
    # consults downstream signals.
    strategy = OnDemandStrategy()
    assert strategy.generator_should_signal(11.0, 100.0, PushPolicy(), _boom) is True
    assert strategy.generator_should_signal(10.0, 100.0, PushPolicy(), _boom) is False


def test_ondemand_generator_signal_pull_needs_downstream_demand():
    strategy = OnDemandStrategy()
    assert strategy.generator_should_signal(
        5.0, 100.0, PullPolicy(), lambda: ["signal"]
    ) is True
    # No downstream signals -> no upstream signal even with waste on hand.
    assert strategy.generator_should_signal(
        50.0, 100.0, PullPolicy(), lambda: []
    ) is False


# --- inventory policy ------------------------------------------------------

def test_push_collection_timeout_always_jitters_without_reading_signals():
    rng = _RecordingRng()
    timeout = PushPolicy().collection_timeout(base_timeout=7.0, has_signals_fn=_boom, rng=rng)
    assert timeout == pytest.approx(9.5)
    assert rng.calls == 1


def test_pull_collection_timeout_skips_jitter_when_signals_pending():
    rng = _RecordingRng()
    timeout = PullPolicy().collection_timeout(
        base_timeout=7.0, has_signals_fn=lambda: True, rng=rng
    )
    assert timeout == 7.0
    assert rng.calls == 0


def test_pull_collection_timeout_jitters_when_no_signals():
    rng = _RecordingRng()
    timeout = PullPolicy().collection_timeout(
        base_timeout=7.0, has_signals_fn=lambda: False, rng=rng
    )
    assert timeout == pytest.approx(9.5)
    assert rng.calls == 1


def test_should_process_kanban_signals_is_pull_only():
    assert PushPolicy().should_process_kanban_signals(["s"]) is False
    assert PullPolicy().should_process_kanban_signals(["s"]) is True
    assert PullPolicy().should_process_kanban_signals([]) is False


def test_push_should_collect_uses_buffered_threshold_without_signals():
    # PUSH threshold = min(0.80, adaptive + 0.10); signals are never read.
    policy = PushPolicy()
    assert policy.collector_should_collect(0.55, 0.50, _boom) is True
    assert policy.collector_should_collect(0.65, 0.50, _boom) is False


def test_pull_should_collect_short_circuits_on_signals():
    policy = PullPolicy()
    # Pending non-market signals force collection regardless of utilization.
    assert policy.collector_should_collect(0.99, 0.50, lambda: ["s"]) is True
    # Otherwise PULL uses the lowered threshold = max(0.15, adaptive - 0.15).
    assert policy.collector_should_collect(0.30, 0.50, lambda: []) is True
    assert policy.collector_should_collect(0.40, 0.50, lambda: []) is False


def test_policy_production_and_signal_propagation_flags():
    assert PushPolicy().propagates_reorder_signals_upstream() is False
    assert PullPolicy().propagates_reorder_signals_upstream() is True
    assert PushPolicy().treatment_is_demand_driven() is False
    assert PullPolicy().treatment_is_demand_driven() is True


def test_policy_clamps_before_delegating_efficiency_curve():
    # The policy owns clamping; verify out-of-range inputs reach the strategy
    # already clamped by checking the curve's clamped-boundary behavior.
    captured = {}

    class _SpyStrategy:
        def collector_push_efficiency(self, utilization, base):
            captured["util"] = utilization
            return base

        def collector_pull_efficiency(self, utilization, signals, base):
            captured["util"] = utilization
            captured["signals"] = signals
            return base

    PushPolicy().collector_efficiency(_SpyStrategy(), utilization=1.5, signals=3, base=1.0)
    assert captured["util"] == 1.0  # clamped to [0, 1]

    PullPolicy().collector_efficiency(_SpyStrategy(), utilization=-0.2, signals=-4, base=1.0)
    assert captured["util"] == 0.0
    assert captured["signals"] == 0  # clamped to >= 0
