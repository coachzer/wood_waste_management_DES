"""Stock-strategy behavior objects (on-demand, reorder-50, reorder-90).

Each concrete class owns the strategy-specific arithmetic that used to live in
``match self.stock_strategy`` blocks across the collector, treatment, and
generator process modules. The methods take primitive values (and, where the
original code only read upstream signals on one branch, a lazy callable) so the
behavior stays byte-identical to the inlined branches it replaces.

Collector efficiency is the same for every strategy and policy (ADR 0025), so
no strategy owns an efficiency curve.
"""

from __future__ import annotations

from typing import Callable, List, Protocol, TYPE_CHECKING

from config.constants import (
    ON_DEMAND_COLLECTOR_BASE_THRESHOLD,
    ON_DEMAND_COLLECTOR_THRESHOLD_GROWTH_PER_DAY,
    ON_DEMAND_COLLECTOR_MAX_THRESHOLD_GROWTH,
    PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_50,
    PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_90,
)
from models.enums import StockStrategy

if TYPE_CHECKING:
    from core.strategies.inventory_policy import InventoryPolicyProtocol


class StockStrategyProtocol(Protocol):
    """The strategy-dependent decisions each process module delegates."""

    def collector_adaptive_threshold(self, base_time: float) -> float:
        """Storage-utilization threshold the collector's should-collect test uses."""
        ...



    def treatment_should_reorder(self, current_total: float, capacity: float) -> bool:
        """Reorder threshold ``s`` of the (s, S) rule on treatment waste storage."""
        ...

    def generator_should_signal(
        self,
        current_storage: float,
        capacity: float,
        inventory_policy: "InventoryPolicyProtocol",
        active_signals_fn: Callable[[], List],
    ) -> bool:
        """Whether the generator emits a collection signal this period."""
        ...


class _ReorderStrategy:
    """Shared behavior for the fixed-fraction reorder strategies.

    The reorder fraction doubles as the collector's adaptive threshold, the
    treatment reorder point fraction, and the generator's signal threshold --
    exactly the literals the three inlined branches used.
    """

    _reorder_fraction: float

    def collector_adaptive_threshold(self, base_time: float) -> float:
        return self._reorder_fraction

    def treatment_should_reorder(self, current_total: float, capacity: float) -> bool:
        return current_total < capacity * self._reorder_fraction

    def generator_should_signal(
        self, current_storage, capacity, inventory_policy, active_signals_fn
    ) -> bool:
        return current_storage >= capacity * self._reorder_fraction


class OnDemandStrategy:
    """Degenerate (s, S) with s = S = capacity: reorder whenever storage is not
    full, for a gap-to-capacity order quantity.  Every consumption triggers a
    replenishment equal to the amount just consumed only as a consequence of
    that degeneracy -- the quantity rule is gap-to-full, not lot-for-lot.
    Lean buffers, responsiveness over utilization."""

    def collector_adaptive_threshold(self, base_time: float) -> float:
        time_factor = min(
            ON_DEMAND_COLLECTOR_MAX_THRESHOLD_GROWTH,
            base_time * ON_DEMAND_COLLECTOR_THRESHOLD_GROWTH_PER_DAY,
        )
        return ON_DEMAND_COLLECTOR_BASE_THRESHOLD + time_factor



    def treatment_should_reorder(self, current_total: float, capacity: float) -> bool:
        return current_total < capacity

    def generator_should_signal(
        self, current_storage, capacity, inventory_policy, active_signals_fn
    ) -> bool:
        return inventory_policy.ondemand_generator_should_signal(
            current_storage, capacity, active_signals_fn
        )


class Reorder50Strategy(_ReorderStrategy):
    """Reorder at 50% of capacity; moderate buffers."""

    _reorder_fraction = PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_50




class Reorder90Strategy(_ReorderStrategy):
    """Reorder at 90% of capacity; large buffers."""

    _reorder_fraction = PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_90




_STOCK_STRATEGY_BY_ENUM = {
    StockStrategy.ON_DEMAND: OnDemandStrategy,
    StockStrategy.REORDER_50: Reorder50Strategy,
    StockStrategy.REORDER_90: Reorder90Strategy,
}


def build_stock_strategy(stock_strategy: StockStrategy) -> StockStrategyProtocol:
    """Map a ``StockStrategy`` enum selector to its behavior object."""
    try:
        return _STOCK_STRATEGY_BY_ENUM[stock_strategy]()
    except KeyError:
        raise ValueError(f"Unknown StockStrategy: {stock_strategy}")
