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
        # Gradually increase threshold over time to trigger more collections.
        time_factor = min(0.3, base_time * 0.001)  # Caps at 30%
        return 0.10 + time_factor  # Start at 10%, grow to 40%

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        # Efficiency depends more on responsiveness than utilization.
        if utilization < 0.1:
            return base * 1.05  # Slight bonus for staying lean
        elif utilization > 0.8:
            return base * 0.95  # Penalty for accumulating too much
        else:
            return base

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        if signals == 0:
            # No demand - minor efficiency loss (idle resources)
            return base * 0.98
        else:
            # More signals = better utilization of ON_DEMAND capabilities
            signal_boost = min(0.15, signals * 0.02)  # Up to 15% efficiency gain

            # Only physical constraints should limit efficiency
            if utilization > 0.95:  # Very close to physical limits
                strain = (utilization - 0.95) * 2.0  # Max 10% penalty at 100%
                return base * (1.0 + signal_boost) * (1.0 - strain)
            else:
                return base * (1.0 + signal_boost)

    def treatment_should_reorder(self, current_total: float, capacity: float) -> bool:
        # ON_DEMAND sets the reorder point ``s`` to full capacity (fires whenever
        # storage is not full).
        return current_total < capacity

    def generator_should_signal(
        self, current_storage, capacity, inventory_policy, active_signals_fn
    ) -> bool:
        # The ON_DEMAND signal trigger depends on the policy: PUSH signals on
        # substantial waste, PULL only when downstream demand exists. Delegating
        # keeps the policy as the single owner of that distinction.
        return inventory_policy.ondemand_generator_should_signal(
            current_storage, capacity, active_signals_fn
        )


class Reorder50Strategy(_ReorderStrategy):
    """Reorder at 50% of capacity; moderate buffers."""

    _reorder_fraction = PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_50

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        # Prefers moderate utilization (30-70% range).
        if 0.3 <= utilization <= 0.7:
            return base * 1.0  # Normal efficiency
        elif utilization < 0.3:
            # Penalty for underutilization
            underutilization_penalty = (0.3 - utilization) * 0.2  # Up to 6% penalty
            return base * (1.0 - underutilization_penalty)
        else:
            # Penalty for overutilization
            overutilization_penalty = (utilization - 0.7) * 0.15  # Up to 4.5% penalty
            return base * (1.0 - overutilization_penalty)

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        # Balanced approach.
        if signals > 0 and 0.3 <= utilization <= 0.7:
            return base * 1.05  # Sweet spot
        elif signals == 0:
            return base * 0.97  # Slight penalty for no demand signals
        else:
            return base


class Reorder90Strategy(_ReorderStrategy):
    """Reorder at 90% of capacity; large buffers."""

    _reorder_fraction = PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_90

    def collector_push_efficiency(self, utilization: float, base: float) -> float:
        # Sweet spot around 85% utilization (80-90% range).
        if 0.8 <= utilization <= 0.9:
            return base * 1.05  # Optimal efficiency
        else:
            # Smooth degradation away from sweet spot
            distance_from_optimal = abs(utilization - 0.85)
            penalty = min(0.3, distance_from_optimal * 0.5)  # Max 30% penalty
            return base * (1.0 - penalty)

    def collector_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        # Benefits from signals but maintains buffer.
        signal_bonus = min(0.1, signals * 0.02)  # Up to 10% bonus

        if utilization > 0.5:
            buffer_bonus = 1.0  # Good buffer maintained
        else:
            buffer_penalty = (0.5 - utilization) * 0.1  # Penalty for low buffer
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
