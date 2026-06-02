"""Inventory-policy behavior objects (PUSH, PULL).

Each concrete class owns the policy-specific decisions that used to live in
``if self.inventory_policy == ...`` / ``match self.inventory_policy`` blocks in
the collector and treatment process modules. Methods take primitive values plus
lazy callables for the few branches where the original code only read kanban
signals on one policy path (``get_signals`` mutates by pruning stale signals, so
it must fire exactly when the original did, no sooner).

The policy owns the PUSH/PULL utilization/signal clamping for the collector
efficiency curve and delegates the strategy-specific shape to the stock
strategy, matching the original ``_calculate_efficiency_multiplier`` split.
"""

from __future__ import annotations

from typing import Callable, List, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from core.strategies.stock_strategy import StockStrategyProtocol
from models.enums import InventoryPolicy


class InventoryPolicyProtocol(Protocol):
    """The policy-dependent decisions the process modules delegate."""

    def collection_timeout(
        self, base_timeout: float, has_signals_fn: Callable[[], bool], rng
    ) -> float:
        """Collector loop wait; PULL skips the jitter draw when signals are pending."""
        ...

    def should_process_kanban_signals(self, kanban_signals: List) -> bool:
        """Whether the collector services kanban signals vs. volume-driven collection."""
        ...

    def collector_should_collect(
        self,
        utilization: float,
        adaptive_threshold: float,
        non_market_signals_fn: Callable[[], List],
    ) -> bool:
        """The collector's per-cycle decision to collect."""
        ...

    def collector_efficiency(
        self,
        stock_strategy: "StockStrategyProtocol",
        utilization: float,
        signals: int,
        base: float,
    ) -> float:
        """Clamp inputs for this policy, then apply the strategy efficiency curve."""
        ...

    def ondemand_generator_should_signal(
        self, current_storage: float, capacity: float, active_signals_fn: Callable[[], List]
    ) -> bool:
        """ON_DEMAND generator signal trigger (policy-specific half of the dispatch)."""
        ...

    def propagates_reorder_signals_upstream(self) -> bool:
        """Whether treatment cascades reorder signals upstream before collecting."""
        ...

    def treatment_is_demand_driven(self) -> bool:
        """Whether treatment produces against consumption events vs. available waste."""
        ...


class PushPolicy:
    """Volume-driven: collectors ignore kanban signals, treatment produces from supply."""

    def collection_timeout(self, base_timeout, has_signals_fn, rng) -> float:
        return base_timeout + rng.uniform(1, 4)

    def should_process_kanban_signals(self, kanban_signals) -> bool:
        return False

    def collector_should_collect(
        self, utilization, adaptive_threshold, non_market_signals_fn
    ) -> bool:
        push_threshold = min(0.80, adaptive_threshold + 0.10)  # +10% buffer for PUSH
        return utilization < push_threshold

    def collector_efficiency(self, stock_strategy, utilization, signals, base) -> float:
        utilization = max(0.0, min(1.0, utilization))
        return stock_strategy.collector_push_efficiency(utilization, base)

    def ondemand_generator_should_signal(
        self, current_storage, capacity, active_signals_fn
    ) -> bool:
        # PUSH ON_DEMAND: signal when we have substantial waste.
        return current_storage > capacity * 0.1

    def propagates_reorder_signals_upstream(self) -> bool:
        return False

    def treatment_is_demand_driven(self) -> bool:
        return False


class PullPolicy:
    """Demand-driven: collectors service kanban signals, treatment produces on consumption."""

    def collection_timeout(self, base_timeout, has_signals_fn, rng) -> float:
        if has_signals_fn():
            return base_timeout
        return base_timeout + rng.uniform(1, 4)

    def should_process_kanban_signals(self, kanban_signals) -> bool:
        return bool(kanban_signals)

    def collector_should_collect(
        self, utilization, adaptive_threshold, non_market_signals_fn
    ) -> bool:
        # Market signals are downstream demand for treatment, not collection
        # requests (ADR 0002, Phase E); the caller has already filtered them out.
        if non_market_signals_fn():
            return True
        # PULL uses much lower thresholds.
        pull_threshold = max(0.15, adaptive_threshold - 0.15)  # -15% for lean operation
        return utilization < pull_threshold

    def collector_efficiency(self, stock_strategy, utilization, signals, base) -> float:
        # Clamp utilization and signals to reasonable ranges.
        utilization = max(0.0, min(1.0, utilization))
        signals = max(0, signals)
        return stock_strategy.collector_pull_efficiency(utilization, signals, base)

    def ondemand_generator_should_signal(
        self, current_storage, capacity, active_signals_fn
    ) -> bool:
        # PULL ON_DEMAND: only signal if we have waste AND downstream demand exists.
        return bool(active_signals_fn()) and current_storage > 0

    def propagates_reorder_signals_upstream(self) -> bool:
        return True

    def treatment_is_demand_driven(self) -> bool:
        return True


_INVENTORY_POLICY_BY_ENUM = {
    InventoryPolicy.PUSH: PushPolicy,
    InventoryPolicy.PULL: PullPolicy,
}


def build_inventory_policy(inventory_policy: InventoryPolicy) -> InventoryPolicyProtocol:
    """Map an ``InventoryPolicy`` enum selector to its behavior object."""
    try:
        return _INVENTORY_POLICY_BY_ENUM[inventory_policy]()
    except KeyError:
        raise ValueError(f"Unknown InventoryPolicy: {inventory_policy}")
