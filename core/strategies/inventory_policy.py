"""Inventory-policy behavior objects (PUSH, PULL).

Each concrete class owns the policy-specific decisions that used to live in
``if self.inventory_policy == ...`` / ``match self.inventory_policy`` blocks in
the collector and treatment process modules. Methods take primitive values plus
lazy callables for the branches that read kanban signals, so PUSH never reads them.

Only the collection trigger differs between the policies. Collector efficiency
is the same for both (ADR 0025).
"""

from __future__ import annotations

from typing import Callable, List, Protocol

from config.constants import (
    COLLECTOR_UTILIZATION_CEILING,
    PUSH_COLLECTOR_THRESHOLD_BUFFER,
    PUSH_ON_DEMAND_GENERATOR_SIGNAL_STORAGE_SHARE,
)

from models.enums import InventoryPolicy


class InventoryPolicyProtocol(Protocol):
    """The policy-dependent decisions the process modules delegate."""

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


    def generators_request_pickup(self) -> bool:
        """Whether a generator may call for pickup on its own stock (ADR 0032)."""
        ...

    def ondemand_generator_should_signal(
        self, current_storage: float, capacity: float, active_signals_fn: Callable[[], List]
    ) -> bool:
        """ON_DEMAND generator signal trigger. Read only when generators request pickup."""
        ...

    def propagates_reorder_signals_upstream(self) -> bool:
        """Whether treatment cascades reorder signals upstream before collecting."""
        ...

    def treatment_is_demand_driven(self) -> bool:
        """Whether treatment produces against consumption events vs. available waste."""
        ...


class PushPolicy:
    """Volume-driven: collectors ignore kanban signals, treatment produces from supply."""

    def should_process_kanban_signals(self, kanban_signals) -> bool:
        return False

    def collector_should_collect(
        self, utilization, adaptive_threshold, non_market_signals_fn
    ) -> bool:
        push_threshold = min(COLLECTOR_UTILIZATION_CEILING, adaptive_threshold + PUSH_COLLECTOR_THRESHOLD_BUFFER)
        return utilization < push_threshold

    def generators_request_pickup(self) -> bool:
        return True

    def ondemand_generator_should_signal(
        self, current_storage, capacity, active_signals_fn
    ) -> bool:
        return current_storage > capacity * PUSH_ON_DEMAND_GENERATOR_SIGNAL_STORAGE_SHARE

    def propagates_reorder_signals_upstream(self) -> bool:
        return False

    def treatment_is_demand_driven(self) -> bool:
        return False


class PullPolicy:
    """Demand-driven: collectors service kanban signals, treatment produces on consumption."""

    def should_process_kanban_signals(self, kanban_signals) -> bool:
        return bool(kanban_signals)

    def collector_should_collect(
        self, utilization, adaptive_threshold, non_market_signals_fn
    ) -> bool:
        if not non_market_signals_fn():
            return False
        return utilization < COLLECTOR_UTILIZATION_CEILING

    def generators_request_pickup(self) -> bool:
        return False

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
