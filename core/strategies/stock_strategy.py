"""Stock-strategy behavior objects (on-demand, reorder-50, reorder-90).

Each concrete class owns the strategy-specific arithmetic that used to live in
``match self.stock_strategy`` blocks across the collector, treatment, and
generator process modules. The methods take primitive values (and, where the
original code only read upstream signals on one branch, a lazy callable) so the
behavior stays byte-identical to the inlined branches it replaces.

The collector efficiency curves receive already-clamped utilization/signal
values from the inventory policy (which owns the PUSH/PULL clamping), matching
the original ``_calculate_push_efficiency`` / ``_calculate_pull_efficiency``
split.
"""

from __future__ import annotations

from typing import Callable, List, Protocol, TYPE_CHECKING

from config.constants import (
    ON_DEMAND_COLLECTOR_BASE_THRESHOLD,
    ON_DEMAND_COLLECTOR_THRESHOLD_GROWTH_PER_DAY,
    ON_DEMAND_COLLECTOR_MAX_THRESHOLD_GROWTH,
    ON_DEMAND_PUSH_IDLE_UTILIZATION,
    ON_DEMAND_PUSH_IDLE_EFFICIENCY_MULTIPLIER,
    ON_DEMAND_PUSH_BUSY_UTILIZATION,
    ON_DEMAND_PUSH_BUSY_EFFICIENCY_MULTIPLIER,
    ON_DEMAND_PULL_NO_SIGNAL_EFFICIENCY_MULTIPLIER,
    ON_DEMAND_PULL_MAX_SIGNAL_BOOST,
    ON_DEMAND_PULL_STRAIN_UTILIZATION,
    ON_DEMAND_PULL_STRAIN_PER_EXCESS_UTILIZATION,
    COLLECTOR_EFFICIENCY_BOOST_PER_PENDING_SIGNAL,
    REORDER_50_OPTIMAL_UTILIZATION_LOW,
    REORDER_50_OPTIMAL_UTILIZATION_HIGH,
    REORDER_50_PUSH_UNDERUTILIZATION_PENALTY_RATE,
    REORDER_50_PUSH_OVERUTILIZATION_PENALTY_RATE,
    REORDER_50_PULL_SIGNALLED_EFFICIENCY_MULTIPLIER,
    REORDER_50_PULL_NO_SIGNAL_EFFICIENCY_MULTIPLIER,
    REORDER_90_OPTIMAL_UTILIZATION_LOW,
    REORDER_90_OPTIMAL_UTILIZATION_HIGH,
    REORDER_90_OPTIMAL_UTILIZATION,
    REORDER_90_PUSH_OPTIMAL_EFFICIENCY_MULTIPLIER,
    REORDER_90_PUSH_PENALTY_PER_DISTANCE_FROM_OPTIMAL,
    REORDER_90_PUSH_MAX_PENALTY,
    REORDER_90_PULL_MAX_SIGNAL_BONUS,
    REORDER_90_PULL_BUFFER_UTILIZATION,
    REORDER_90_PULL_BUFFER_PENALTY_RATE,
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

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        """PUSH efficiency curve; ``utilization`` is pre-clamped to [0, 1]."""
        ...

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        """PULL efficiency curve; ``utilization`` and ``signals`` are pre-clamped."""
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

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        if utilization < ON_DEMAND_PUSH_IDLE_UTILIZATION:
            return base * ON_DEMAND_PUSH_IDLE_EFFICIENCY_MULTIPLIER
        elif utilization > ON_DEMAND_PUSH_BUSY_UTILIZATION:
            return base * ON_DEMAND_PUSH_BUSY_EFFICIENCY_MULTIPLIER
        else:
            return base

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        if signals == 0:
            return base * ON_DEMAND_PULL_NO_SIGNAL_EFFICIENCY_MULTIPLIER
        else:
            signal_boost = min(
                ON_DEMAND_PULL_MAX_SIGNAL_BOOST, signals * COLLECTOR_EFFICIENCY_BOOST_PER_PENDING_SIGNAL
            )

            if utilization > ON_DEMAND_PULL_STRAIN_UTILIZATION:
                strain = (
                    (utilization - ON_DEMAND_PULL_STRAIN_UTILIZATION) * ON_DEMAND_PULL_STRAIN_PER_EXCESS_UTILIZATION
                )
                return base * (1.0 + signal_boost) * (1.0 - strain)
            else:
                return base * (1.0 + signal_boost)

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

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        if REORDER_50_OPTIMAL_UTILIZATION_LOW <= utilization <= REORDER_50_OPTIMAL_UTILIZATION_HIGH:
            return base * 1.0
        elif utilization < REORDER_50_OPTIMAL_UTILIZATION_LOW:
            underutilization_penalty = (
                (REORDER_50_OPTIMAL_UTILIZATION_LOW - utilization) * REORDER_50_PUSH_UNDERUTILIZATION_PENALTY_RATE
            )
            return base * (1.0 - underutilization_penalty)
        else:
            overutilization_penalty = (
                (utilization - REORDER_50_OPTIMAL_UTILIZATION_HIGH) * REORDER_50_PUSH_OVERUTILIZATION_PENALTY_RATE
            )
            return base * (1.0 - overutilization_penalty)

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        if signals > 0 and REORDER_50_OPTIMAL_UTILIZATION_LOW <= utilization <= REORDER_50_OPTIMAL_UTILIZATION_HIGH:
            return base * REORDER_50_PULL_SIGNALLED_EFFICIENCY_MULTIPLIER
        elif signals == 0:
            return base * REORDER_50_PULL_NO_SIGNAL_EFFICIENCY_MULTIPLIER
        else:
            return base


class Reorder90Strategy(_ReorderStrategy):
    """Reorder at 90% of capacity; large buffers."""

    _reorder_fraction = PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_90

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        if REORDER_90_OPTIMAL_UTILIZATION_LOW <= utilization <= REORDER_90_OPTIMAL_UTILIZATION_HIGH:
            return base * REORDER_90_PUSH_OPTIMAL_EFFICIENCY_MULTIPLIER
        else:
            distance_from_optimal = abs(utilization - REORDER_90_OPTIMAL_UTILIZATION)
            penalty = min(
                REORDER_90_PUSH_MAX_PENALTY,
                distance_from_optimal * REORDER_90_PUSH_PENALTY_PER_DISTANCE_FROM_OPTIMAL,
            )
            return base * (1.0 - penalty)

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        signal_bonus = min(REORDER_90_PULL_MAX_SIGNAL_BONUS, signals * COLLECTOR_EFFICIENCY_BOOST_PER_PENDING_SIGNAL)

        if utilization > REORDER_90_PULL_BUFFER_UTILIZATION:
            buffer_bonus = 1.0
        else:
            buffer_penalty = (REORDER_90_PULL_BUFFER_UTILIZATION - utilization) * REORDER_90_PULL_BUFFER_PENALTY_RATE
            buffer_bonus = 1.0 - buffer_penalty

        return base * (1.0 + signal_bonus) * buffer_bonus


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
