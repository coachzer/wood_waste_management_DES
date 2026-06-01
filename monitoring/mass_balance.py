"""Product mass-balance invariant monitor (ADR 0002, Phase E.5).

Asserts, per treatment operator and product, that finished-goods mass is
conserved across a simulation run:

    initial_finished_goods + cumulative_produced
        == cumulative_consumed + current_finished_goods + production_discarded

The left side is everything that has entered inventory (the primed initial
stock plus all production); the right side is everything that is accounted for
(consumed by the market, still in storage, or explicitly discarded). A mismatch
means mass appeared or vanished without a recorded reason.

The monitor is the regression net for retiring the legacy demand-ceiling code:
it construction-snapshots the primed inventory, then checks the identity every
consumption tick and at end of run. Only the product invariant is implemented
here; the waste-side invariant stays deferred (ADR 0002, P2).
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from models.enums import OutputType

# Mixed tolerance: rel_tol handles accumulated float error at scale, abs_tol
# keeps near-zero early-run states (empty products) from false-tripping.
RELATIVE_TOLERANCE = 1e-6
ABSOLUTE_TOLERANCE = 1e-9


class MassBalanceViolation(Exception):
    """Raised when the product mass-balance identity does not hold.

    A custom exception, not ``assert`` -- assertions are stripped under ``-O``,
    and the monitor is a safety net that must hold in every run mode.
    """


@dataclass
class EntityRegistry:
    """Injection seam for the monitor (ADR 0002, line 41).

    The product invariant reads only ``state`` and ``operators``; the
    waste-side fields are carried per the ADR for the deferred waste invariant
    (P2) and default to ``None`` so the product-only seam stays minimal.
    """

    state: Any
    operators: List[Any]
    generators: Optional[List[Any]] = None
    collectors: Optional[List[Any]] = None
    transport: Optional[List[Any]] = None


class MassBalanceMonitor:
    """Checks the per-product finished-goods mass-balance invariant.

    Constructed from an :class:`EntityRegistry`. Snapshots each operator's
    primed initial finished-goods inventory at construction (simulation start,
    after priming), then compares the conservation identity on demand.
    """

    def __init__(self, registry: EntityRegistry, raise_on_violation: bool = True) -> None:
        """Capture the initial finished-goods snapshot.

        ``raise_on_violation`` defaults to ``True`` (development / single runs);
        batch Monte Carlo passes ``False`` so one bad seed warns and continues
        rather than aborting the remaining replications.
        """
        self.registry = registry
        self.raise_on_violation = raise_on_violation
        # Per-check telemetry: (timestamp, operator, product, lhs, rhs, delta),
        # emitted on every check so drift is visible before it crosses tolerance.
        self.telemetry: List[Tuple[Optional[float], str, str, float, float, float]] = []
        self._initial_finished_goods = {
            operator.name: {
                product: operator.finished_goods.current_storage[OutputType(product)]
                for product in operator.product_volumes
            }
            for operator in registry.operators
        }

    def check_continuous(self, timestamp: Optional[float] = None) -> None:
        """Scheduled per-tick check. Records telemetry and raises/warns on drift."""
        self._check(timestamp)

    def check_final(self, timestamp: Optional[float] = None) -> None:
        """End-of-run check. Identical to the scheduled check; no scheduling."""
        self._check(timestamp)

    def _check(self, timestamp: Optional[float]) -> None:
        state = self.registry.state
        violations = []
        for operator in self.registry.operators:
            for product in operator.product_volumes:
                initial = self._initial_finished_goods[operator.name][product]
                produced = operator.product_volumes[product]
                consumed = sum(
                    event["consumed"]
                    for event in state.consumption_events
                    if event["operator"] == operator.name and event["product"] == product
                )
                current = operator.finished_goods.current_storage[OutputType(product)]
                discarded = state.production_discarded[product]

                lhs = initial + produced
                rhs = consumed + current + discarded
                delta = lhs - rhs
                self.telemetry.append((timestamp, operator.name, product, lhs, rhs, delta))

                if not math.isclose(
                    lhs, rhs, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE
                ):
                    violations.append(
                        f"{operator.name}/{product}: in={lhs:.6f} out={rhs:.6f} "
                        f"delta={delta:.6f}"
                    )

        if not violations:
            return
        message = (
            f"Product mass-balance violated at t={timestamp}: " + "; ".join(violations)
        )
        if self.raise_on_violation:
            raise MassBalanceViolation(message)
        logging.warning(message)
