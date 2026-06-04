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
consumption tick and at end of run. The product invariant runs every tick; the
per-collection-center and system-wide waste invariants are final-only (run on a
drained simulation, see their docstrings).
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
        # Initial raw-waste on hand per collection center (collection centers start
        # empty, but snapshotting keeps the waste invariant symmetric with the
        # product one and robust to a primed start).
        self._initial_collection_center = {
            collector.name: sum(collector.collection_center.current_storage.values())
            for collector in (registry.collectors or [])
        }
        # Initial raw waste primed into treatment storage (system-wide). Generator
        # initial stock is already folded into each generator's total_generated,
        # so only the treatment side needs a snapshot for the waste-side identity.
        # getattr-guarded so product-only operator stubs (no waste_storage) read 0.
        self._initial_treatment_waste_storage = sum(
            sum(getattr(operator, "waste_storage", {}).values())
            for operator in registry.operators
        )

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

    def check_collection_centers(self, timestamp: Optional[float] = None) -> None:
        """Check the per-collection-center raw-waste conservation identity.

        For each collector:

            initial_storage + inflow
                == outflow + current_storage + landfilled

        ``inflow`` is every transport flow targeting the collector (collection
        from generators plus cross-region reposition-in); ``outflow`` is every
        flow sourced from it (treatment intake plus reposition-out). The
        expand-drop leak (issue 11, Finding A) makes inflow exceed the
        accounted-for terms, so this trips on dropped collected waste.

        Final-only by intent: cross-region reposition is logged at request time
        but physically re-deposited at arrival, so an in-transit volume would
        false-trip a mid-run check. Run on a drained simulation.
        """
        state = self.registry.state
        violations = []
        for collector in (self.registry.collectors or []):
            name = collector.name
            inflow = sum(
                flow["volume"] for flow in state.transport_flows
                if flow["target_name"] == name
            )
            outflow = sum(
                flow["volume"] for flow in state.transport_flows
                if flow["source_name"] == name
            )
            initial = self._initial_collection_center[name]
            current = sum(collector.collection_center.current_storage.values())
            landfilled = state.waste_landfilled.get(name, 0.0)

            lhs = initial + inflow
            rhs = outflow + current + landfilled
            delta = lhs - rhs
            self.telemetry.append((timestamp, name, "raw_waste", lhs, rhs, delta))

            if not math.isclose(
                lhs, rhs, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE
            ):
                violations.append(
                    f"{name}: in={lhs:.6f} out={rhs:.6f} delta={delta:.6f}"
                )

        if not violations:
            return
        message = (
            f"Collection-center mass-balance violated at t={timestamp}: "
            + "; ".join(violations)
        )
        if self.raise_on_violation:
            raise MassBalanceViolation(message)
        logging.warning(message)

    def check_waste_system(self, timestamp: Optional[float] = None) -> None:
        """Check the system-wide waste-side mass-balance identity (ADR 0002, P2).

        Raw waste is conserved across the whole system: everything generated
        (plus any raw waste primed into treatment at t=0) must equal the sum of
        every fate -- raw waste still resident at each echelon, consumed by
        treatment, or landfilled:

            sum(generated) + initial_treatment_storage + initial_collection_center
                == generator_storage + in_transit + collection_center_storage
                 + treatment_storage + treated_intake + landfilled

        The left side is everything that entered the waste system: all committed
        generation (which already folds in primed generator stock) plus raw
        waste primed elsewhere. The right side is every fate -- raw waste on hand
        in generators, on vehicles in transit (C2's per-type accounting), in
        collection centers, and in treatment storage; raw waste consumed by
        treatment transformation (``processed_volumes``, the corrected intake of
        ADR 0009 and a terminal sink); and raw waste landfilled on storage
        overflow (``state.waste_landfilled``, the single funnel through
        ``handle_storage_event``). A mismatch means raw waste appeared or
        vanished without a recorded reason.

        Final-only by intent: run on a drained simulation. The in-transit term
        keeps cross-region repositioning accounted, so the identity holds at any
        settled tick, but it is checked at end of run alongside the product
        check rather than on a per-tick cadence.
        """
        state = self.registry.state
        generators = self.registry.generators or []
        collectors = self.registry.collectors or []
        operators = self.registry.operators

        generated = sum(
            sum(generator.total_generated.values()) for generator in generators
        )
        generator_storage = sum(generator.current_storage for generator in generators)
        in_transit = sum(
            sum(vehicle.current_load_by_type.values())
            for vehicle in state.iter_outbound_vehicles()
        )
        collection_center_storage = sum(
            sum(collector.collection_center.current_storage.values())
            for collector in collectors
        )
        treatment_storage = sum(
            sum(operator.waste_storage.values()) for operator in operators
        )
        treated_intake = sum(
            sum(operator.processed_volumes.values()) for operator in operators
        )
        landfilled = sum(state.waste_landfilled.values())
        initial_collection_center = sum(self._initial_collection_center.values())

        lhs = generated + self._initial_treatment_waste_storage + initial_collection_center
        rhs = (
            generator_storage
            + in_transit
            + collection_center_storage
            + treatment_storage
            + treated_intake
            + landfilled
        )
        delta = lhs - rhs
        self.telemetry.append((timestamp, "system", "raw_waste", lhs, rhs, delta))

        if math.isclose(lhs, rhs, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE):
            return
        message = (
            f"Waste-side mass-balance violated at t={timestamp}: "
            f"in={lhs:.6f} out={rhs:.6f} delta={delta:.6f}"
        )
        if self.raise_on_violation:
            raise MassBalanceViolation(message)
        logging.warning(message)

    def check_yield_bridge(self, timestamp: Optional[float] = None) -> None:
        """Check the waste->product yield bridge, per treatment operator (G1).

        The product and waste invariants each close independently; neither
        relates intake to output. This check is the bridge between them:

            expected_output_volume == sum(product_volumes.values())

        ``expected_output_volume`` is accumulated on the operator as
        ``intake x efficiency`` at each transformation -- an expectation derived
        straight from the intake, independent of the path that deposits finished
        goods (``_calculate_output_amounts``). The right side is the finished
        goods actually produced. In correct code the two agree; a wrong
        conversion efficiency or a mis-scaled yield makes the deposited output
        diverge from the intake-derived expectation and trips here, where the
        single-ledger invariants stay silent.

        Final-only by intent: a single end-of-run reconciliation of the two
        cumulative counters; there is no per-tick term to drift.
        """
        violations = []
        for operator in self.registry.operators:
            expected = getattr(operator, "expected_output_volume", 0.0)
            produced = sum(operator.product_volumes.values())
            delta = expected - produced
            self.telemetry.append(
                (timestamp, operator.name, "yield_bridge", expected, produced, delta)
            )

            if not math.isclose(
                expected, produced, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE
            ):
                violations.append(
                    f"{operator.name}: expected={expected:.6f} "
                    f"produced={produced:.6f} delta={delta:.6f}"
                )

        if not violations:
            return
        message = (
            f"Yield-bridge mass-balance violated at t={timestamp}: "
            + "; ".join(violations)
        )
        if self.raise_on_violation:
            raise MassBalanceViolation(message)
        logging.warning(message)
