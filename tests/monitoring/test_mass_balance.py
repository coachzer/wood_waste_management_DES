"""Tests for the product mass-balance invariant monitor (ADR 0002, Phase E.5).

The invariant, per treatment operator and product, is:

    initial_finished_goods + cumulative_produced
        == cumulative_consumed + current_finished_goods + production_discarded

These tests drive a state through the ``EntityRegistry`` seam -- the injection
boundary ADR 0002 designed -- so the invariant can be exercised without a SimPy
clock. Lightweight stand-ins quack like the real entities the monitor reads.
"""

from types import SimpleNamespace

from models.enums import OutputType
from monitoring.mass_balance import (
    EntityRegistry,
    MassBalanceMonitor,
    MassBalanceViolation,
)


def make_operator(name, produced, storage):
    """A minimal treatment-operator stand-in the monitor can read.

    ``produced`` maps product strings to the uncapped output counter;
    ``storage`` maps product strings to current finished-goods volume.
    """
    finished_goods = SimpleNamespace(
        current_storage={OutputType(product): volume for product, volume in storage.items()}
    )
    return SimpleNamespace(
        name=name,
        product_volumes=dict(produced),
        finished_goods=finished_goods,
    )


def make_state(operator):
    """A minimal SimulationState stand-in: an event log and a discard counter."""
    return SimpleNamespace(
        consumption_events=[],
        production_discarded={"mdf": 0.0, "particle_board": 0.0, "osb": 0.0},
        treatment_operators=[operator],
    )


def test_violating_invariant_raises():
    """Finished goods leaving inventory with no matching consumption event
    breaks the invariant and must raise."""
    operator = make_operator(
        name="op-1",
        produced={"mdf": 0.0, "particle_board": 0.0, "osb": 0.0},
        storage={"mdf": 100.0, "particle_board": 0.0, "osb": 0.0},
    )
    state = make_state(operator)
    monitor = MassBalanceMonitor(EntityRegistry(state=state, operators=[operator]))

    # Inventory drops by 30 with no consumption event recorded -- mass vanishes.
    operator.finished_goods.current_storage[OutputType.MDF] -= 30.0

    try:
        monitor.check_final()
    except MassBalanceViolation:
        return
    raise AssertionError("expected MassBalanceViolation for unaccounted inventory loss")


def test_valid_invariant_does_not_raise():
    """Finished goods leaving inventory with a matching consumption event
    conserves mass and must not raise."""
    operator = make_operator(
        name="op-1",
        produced={"mdf": 0.0, "particle_board": 0.0, "osb": 0.0},
        storage={"mdf": 100.0, "particle_board": 0.0, "osb": 0.0},
    )
    state = make_state(operator)
    monitor = MassBalanceMonitor(EntityRegistry(state=state, operators=[operator]))

    # Inventory drops by 30, recorded as a market consumption of 30 -- balanced.
    operator.finished_goods.current_storage[OutputType.MDF] -= 30.0
    state.consumption_events.append(
        {"operator": "op-1", "product": "mdf", "consumed": 30.0}
    )

    monitor.check_final()  # must not raise


# --- collection-center raw-waste invariant (ADR 0009, issue 11) -------------
#
# Per collection center:
#     initial_storage + inflow == outflow + current_storage + landfilled
# inflow  = transport flows targeting the collector (collection + reposition-in)
# outflow = transport flows sourced from the collector (treatment intake +
#           reposition-out). The expand-drop leak makes inflow exceed the
#           accounted-for terms, which this check catches.


def make_collector(name, storage):
    """A collector stand-in exposing the collection center the invariant reads."""
    return SimpleNamespace(
        name=name,
        collection_center=SimpleNamespace(current_storage=dict(storage)),
    )


def make_waste_state():
    """A SimulationState stand-in: a transport-flow log and a landfill counter."""
    return SimpleNamespace(transport_flows=[], waste_landfilled={})


def flow(source, target, volume):
    return {"source_name": source, "target_name": target, "volume": volume}


def test_balanced_collection_center_does_not_raise():
    """Inflow accounted for by treatment outflow, on-hand storage, and landfill
    -- the center conserves raw waste and must not raise."""
    collector = make_collector("collector-1", {"17 02 01": 0.0})
    state = make_waste_state()
    monitor = MassBalanceMonitor(
        EntityRegistry(state=state, operators=[], collectors=[collector])
    )

    # 1000 collected in; 700 drawn to treatment, 100 landfilled, 200 left on hand.
    state.transport_flows.extend(
        [flow("gen-1", "collector-1", 1000.0), flow("collector-1", "treatment-1", 700.0)]
    )
    state.waste_landfilled["collector-1"] = 100.0
    collector.collection_center.current_storage["17 02 01"] = 200.0

    monitor.check_collection_centers()  # must not raise


def test_dropped_overflow_trips_collection_center_invariant():
    """Mass collected but neither stored, sent to treatment, nor landfilled --
    the expand-drop leak class -- must raise."""
    collector = make_collector("collector-1", {"17 02 01": 0.0})
    state = make_waste_state()
    monitor = MassBalanceMonitor(
        EntityRegistry(state=state, operators=[], collectors=[collector])
    )

    # 1000 collected in; 700 to treatment, 200 on hand, but the 100 overflow was
    # silently dropped (not landfilled) -- mass vanishes.
    state.transport_flows.extend(
        [flow("gen-1", "collector-1", 1000.0), flow("collector-1", "treatment-1", 700.0)]
    )
    collector.collection_center.current_storage["17 02 01"] = 200.0

    try:
        monitor.check_collection_centers()
    except MassBalanceViolation:
        return
    raise AssertionError("expected MassBalanceViolation for dropped collection-center waste")
