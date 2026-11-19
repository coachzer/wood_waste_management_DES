"""Product mass-balance invariant monitor (ADR 0002, Phase E.5).

Asserts, per treatment operator and product, that finished-goods mass is
conserved across a simulation run:

    initial_finished_goods + cumulative_produced
        == cumulative_consumed + current_finished_goods

There is no discard term: finished goods have no disposal path, and the
treatment yield loss is applied before deposit (untracked by design -- a
documented model limitation, not conserved mass).
A mismatch means mass appeared or vanished without a recorded reason. The monitor
construction-snapshots the primed inventory, then checks the identity every
consumption tick and at end of run. The product invariant runs every tick; the
per-collection-center and system-wide waste invariants are final-only (run on a
drained simulation, see their docstrings).
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from instrumentation.history_store import HistoryStore
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
    ``history`` is the run's :class:`HistoryStore`, whose landfill ledger is
    the raw-waste discard term of the waste invariants (ADR 0009); absent, no
    landfill is assumed.
    """

    state: Any
    operators: List[Any]
    generators: Optional[List[Any]] = None
    collectors: Optional[List[Any]] = None
    history: Optional[HistoryStore] = None

    def landfilled_by_entity(self) -> Dict[str, float]:
        """Raw waste landfilled per entity (m3), from the landfill ledger."""
        if self.history is None:
            return {}
        return self.history.landfilled_volume_by_entity()


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

                lhs = initial + produced
                rhs = consumed + current
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
        plus cross-region reposition-in); ``outflow`` every flow sourced from it
        (treatment intake plus reposition-out). Cross-region reposition logged as
        inflow here but still on a vehicle is added to ``out``. Reposition still
        queued for a vehicle is in the origin's ``current_storage``. Final-only by intent.
        """
        state = self.registry.state
        landfilled_by_entity = self.registry.landfilled_by_entity()
        in_flight_by_destination = state.scheduled_reposition_volume_by_destination()
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
            landfilled = landfilled_by_entity.get(name, 0.0)

            in_pipeline = in_flight_by_destination.get(name, 0.0)

            lhs = initial + inflow
            rhs = outflow + current + landfilled + in_pipeline
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

        Raw waste is conserved across the whole system: everything generated (plus
        any raw waste primed into treatment at t=0) equals the sum of every fate:

            sum(generated) + initial_treatment_storage + initial_collection_center
                == generator_storage + in_transit + collection_center_storage
                 + treatment_storage + treated_intake + landfilled

        ``treated_intake`` is ``processed_volumes`` (the corrected ADR 0009
        intake); ``landfilled`` is the single funnel through
        ``handle_storage_event``, read from the landfill ledger. A mismatch means raw waste appeared or vanished
        without a recorded reason. ``in_transit`` covers loaded vehicles.
        Repositioning still queued for a vehicle stays in its origin center.
        Final-only by intent.
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
        landfilled = sum(self.registry.landfilled_by_entity().values())
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

    def check_generators(self, timestamp: Optional[float] = None) -> None:
        """Check that every generator accounts for all the waste it generated.

        Per generator and waste type:

            total_potential_generated == total_generated + total_uncollected + total_outlet

        ``total_generated`` is the waste that entered generator storage.
        ``total_uncollected`` is the waste generated while storage was full,
        which leaves the modelled system without a destination (ADR 0024).
        ``total_outlet`` is waste of a type no processor accepts, which leaves
        at the generator without entering storage (ADR 0036).
        Both accumulate separately, so a generation path that drops or invents
        waste trips here.
        """
        violations = []
        for generator in self.registry.generators or []:
            for waste_type, potential in generator.total_potential_generated.items():
                accounted = (
                    generator.total_generated[waste_type]
                    + generator.total_uncollected[waste_type]
                    + generator.total_outlet[waste_type]
                )
                delta = potential - accounted
                self.telemetry.append(
                    (timestamp, generator.name, f"generation/{waste_type.value}", potential, accounted, delta)
                )
                if not math.isclose(
                    potential, accounted, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE
                ):
                    violations.append(
                        f"{generator.name}/{waste_type.value}: potential={potential:.6f} "
                        f"accounted={accounted:.6f} delta={delta:.6f}"
                    )

        if not violations:
            return
        message = (
            f"Generator mass-balance violated at t={timestamp}: " + "; ".join(violations)
        )
        if self.raise_on_violation:
            raise MassBalanceViolation(message)
        logging.warning(message)

    def check_yield_bridge(self, timestamp: Optional[float] = None) -> None:
        """Check the waste->product yield bridge, per treatment operator (G1).

        The product and waste invariants each close independently; neither
        relates intake to output. This check is the bridge between them:

            expected_output_volume_from_intake_m3 == sum(product_volumes.values())

        ``expected_output_volume_from_intake_m3`` accumulates ``intake x efficiency`` at each
        transformation, independent of the deposit path. A wrong conversion
        efficiency or mis-scaled yield makes deposited output diverge from this
        intake-derived expectation and trips here, where the single-ledger
        invariants stay silent.

        Final-only by intent: a single end-of-run reconciliation of the two
        cumulative counters; there is no per-tick term to drift.
        """
        violations = []
        for operator in self.registry.operators:
            expected = getattr(operator, "expected_output_volume_from_intake_m3", 0.0)
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
