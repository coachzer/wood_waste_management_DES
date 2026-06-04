"""Tests for the product mass-balance invariant monitor (ADR 0002, Phase E.5).

The invariant, per treatment operator and product, is:

    initial_finished_goods + cumulative_produced
        == cumulative_consumed + current_finished_goods + production_discarded

These tests drive a state through the ``EntityRegistry`` seam -- the injection
boundary ADR 0002 designed -- so the invariant can be exercised without a SimPy
clock. Lightweight stand-ins quack like the real entities the monitor reads.
"""

from types import SimpleNamespace

import pytest

from models.enums import InventoryPolicy, OutputType, StockStrategy
from monitoring.mass_balance import (
    EntityRegistry,
    MassBalanceMonitor,
    MassBalanceViolation,
)


def make_operator(name, produced, storage, expected_output=None):
    """A minimal treatment-operator stand-in the monitor can read.

    ``produced`` maps product strings to the uncapped output counter;
    ``storage`` maps product strings to current finished-goods volume.
    ``expected_output`` is the yield-bridge accumulator (intake x efficiency);
    left unset by tests that do not exercise ``check_yield_bridge``.
    """
    finished_goods = SimpleNamespace(
        current_storage={OutputType(product): volume for product, volume in storage.items()}
    )
    operator = SimpleNamespace(
        name=name,
        product_volumes=dict(produced),
        finished_goods=finished_goods,
    )
    if expected_output is not None:
        operator.expected_output_volume = expected_output
    return operator


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


# --- waste->product yield-bridge invariant (G1) -----------------------------
#
# Per treatment operator, the bridge relates the two otherwise-independent
# ledgers: the output expected from intake (intake x efficiency, accumulated
# into expected_output_volume) must equal the finished-goods actually deposited
# (sum of product_volumes). A wrong efficiency or mis-scaled yield breaks the
# bridge without disturbing either single-ledger invariant.


def test_yield_bridge_mismatch_trips():
    """Deposited product mass below the intake x efficiency expectation -- a
    mis-scaled yield, the gap the bridge exists to catch -- must raise."""
    operator = make_operator(
        name="op-1",
        produced={"mdf": 50.0, "particle_board": 0.0, "osb": 0.0},
        storage={"mdf": 50.0, "particle_board": 0.0, "osb": 0.0},
        expected_output=100.0,
    )
    state = make_state(operator)
    monitor = MassBalanceMonitor(EntityRegistry(state=state, operators=[operator]))

    try:
        monitor.check_yield_bridge()
    except MassBalanceViolation:
        return
    raise AssertionError("expected MassBalanceViolation for yield-bridge mismatch")


def test_yield_bridge_balanced_does_not_raise():
    """Deposited product mass equal to the intake x efficiency expectation --
    the bridge closes and must not raise."""
    operator = make_operator(
        name="op-1",
        produced={"mdf": 100.0, "particle_board": 0.0, "osb": 0.0},
        storage={"mdf": 100.0, "particle_board": 0.0, "osb": 0.0},
        expected_output=100.0,
    )
    state = make_state(operator)
    monitor = MassBalanceMonitor(EntityRegistry(state=state, operators=[operator]))

    monitor.check_yield_bridge()  # must not raise


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


# --- system-wide waste-side invariant (C3) ----------------------------------
#
# sum(generated) + initial_treatment_storage + initial_collection_center
#     == generator_storage + in_transit + collection_center_storage
#      + treatment_storage + treated_intake + landfilled
#
# generated folds in primed generator stock; the right side is every fate of a
# unit of raw waste -- resident at an echelon, in transit, consumed by
# treatment, or landfilled. The stubs are primed empty at construction, then
# mutated to replay a run so the snapshot terms stay zero and the run terms
# carry the whole balance.

WT = "17 02 01"  # WasteType.CONSTRUCTION_WOOD_17_02_01 value


def make_generator(name, generated, storage):
    """A generator stub: cumulative generation per type + scalar on-hand storage."""
    return SimpleNamespace(name=name, total_generated=dict(generated), current_storage=storage)


def make_treatment_op(name, waste_storage, processed):
    """A treatment-operator stub carrying both the product fields the monitor's
    constructor snapshots (empty here) and the waste fields the waste check reads."""
    return SimpleNamespace(
        name=name,
        product_volumes={},
        finished_goods=SimpleNamespace(current_storage={}),
        waste_storage=dict(waste_storage),
        processed_volumes=dict(processed),
    )


def make_system_state(vehicles=(), landfilled=None):
    """A SimulationState stub exposing the in-transit iterator and landfill log."""
    moving = list(vehicles)
    return SimpleNamespace(
        iter_outbound_vehicles=lambda: iter(moving),
        waste_landfilled=dict(landfilled or {}),
    )


def build_waste_monitor():
    """Construct a monitor over empty-primed stubs and return (monitor, refs).

    Everything is primed at zero so the construction snapshots are zero and a
    replayed run is expressed entirely through the mutable run terms.
    """
    generator = make_generator("gen-1", {WT: 0.0}, 0.0)
    collector = make_collector("col-1", {WT: 0.0})
    operator = make_treatment_op("op-1", {WT: 0.0}, {WT: 0.0})
    state = make_system_state()
    monitor = MassBalanceMonitor(
        EntityRegistry(
            state=state,
            operators=[operator],
            generators=[generator],
            collectors=[collector],
        )
    )
    return monitor, state, generator, collector, operator


def test_balanced_waste_system_does_not_raise():
    """Every generated unit resolves to exactly one fate -- conserved, no raise."""
    monitor, state, generator, collector, operator = build_waste_monitor()

    # Generate 1000; fates: 300 still in generator, 200 in a collection center,
    # 50 on a vehicle in transit, 100 in treatment storage, 150 consumed by
    # treatment, 200 landfilled. 300+200+50+100+150+200 == 1000.
    generator.total_generated[WT] = 1000.0
    generator.current_storage = 300.0
    collector.collection_center.current_storage[WT] = 200.0
    operator.waste_storage[WT] = 100.0
    operator.processed_volumes[WT] = 150.0
    state.waste_landfilled["col-1"] = 200.0
    vehicle = SimpleNamespace(current_load_by_type={WT: 50.0})
    state.iter_outbound_vehicles = lambda: iter([vehicle])

    monitor.check_waste_system()  # must not raise


def test_leaking_waste_system_trips():
    """A unit of generated waste with no recorded fate -- the leak class the
    invariant exists to catch -- must raise."""
    monitor, state, generator, collector, operator = build_waste_monitor()

    # Same as the balanced case but 50 of the landfilled volume is dropped
    # (150 recorded, not 200) -- mass vanishes with no fate.
    generator.total_generated[WT] = 1000.0
    generator.current_storage = 300.0
    collector.collection_center.current_storage[WT] = 200.0
    operator.waste_storage[WT] = 100.0
    operator.processed_volumes[WT] = 150.0
    state.waste_landfilled["col-1"] = 150.0
    vehicle = SimpleNamespace(current_load_by_type={WT: 50.0})
    state.iter_outbound_vehicles = lambda: iter([vehicle])

    try:
        monitor.check_waste_system()
    except MassBalanceViolation:
        return
    raise AssertionError("expected MassBalanceViolation for unaccounted generated waste")


@pytest.mark.slow
def test_yield_bridge_trips_on_halved_yield(monkeypatch):
    """A mis-scaled yield is caught end-to-end (connection-audit Probe 4).

    Monkeypatching ``_calculate_output_amounts`` to halve the deposited output
    leaves intake (and thus ``expected_output_volume``) untouched, so the
    finished goods diverge from the intake-derived expectation. Probe 4 showed
    this slips past both single-ledger invariants; the armed yield bridge must
    abort the run (surfaced as ``SystemExit`` whose cause is a
    ``MassBalanceViolation``). Slow: a full 365-day, 12-region simulation.
    """
    from core.treatment import TreatmentOperator
    from main import run_single_simulation

    def halved_output(self, amount_to_process, efficiency):
        return amount_to_process, amount_to_process * efficiency * 0.5

    monkeypatch.setattr(TreatmentOperator, "_calculate_output_amounts", halved_output)

    with pytest.raises(SystemExit) as excinfo:
        run_single_simulation(
            scenario_name="Baseline",
            inventory_policy=InventoryPolicy.PUSH,
            stock_strategy=StockStrategy.ON_DEMAND,
            seed=123456,
            create_mfa=False,
            raise_on_violation=True,
        )

    cause = excinfo.value.__cause__
    assert isinstance(cause, MassBalanceViolation)
    assert "Yield-bridge" in str(cause)


@pytest.mark.slow
def test_yield_bridge_holds_on_baseline_run():
    """The armed yield bridge closes on a real, unmutated baseline run.

    ``run_single_simulation`` runs with ``raise_on_violation=True``, so the
    end-of-run ``check_yield_bridge`` aborts (as ``SystemExit``) on any
    intake/output divergence; a clean return means deposited finished goods
    match the intake x efficiency expectation. Slow: a full baseline run.
    """
    from main import run_single_simulation

    result = run_single_simulation(
        scenario_name="Baseline",
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.ON_DEMAND,
        seed=123456,
        create_mfa=False,
        raise_on_violation=True,
    )
    assert result["scenario_name"]


@pytest.mark.slow
def test_waste_system_invariant_holds_on_baseline_run():
    """The armed waste-side invariant holds on a real drained baseline run.

    ``run_single_simulation`` runs with ``raise_on_violation=True``, so the
    end-of-run ``check_waste_system`` aborts (surfaced as ``SystemExit``) on any
    leak; a clean return means raw waste is conserved system-wide. Slow: a full
    365-day, 12-region simulation.
    """
    from main import run_single_simulation

    result = run_single_simulation(
        scenario_name="Baseline",
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.ON_DEMAND,
        seed=123456,
        create_mfa=False,
        raise_on_violation=True,
    )
    assert result["scenario_name"]


@pytest.mark.slow
def test_collection_center_invariant_holds_on_baseline_run():
    """The per-collection-center identity closes on a real drained baseline run.

    Wired final-only in ``run_simulation`` alongside ``check_waste_system``. With
    reposition outflow now sourced on the origin collector (not the borrowed
    carrier), each center's books balance independently. ``raise_on_violation``
    aborts (as ``SystemExit``) on any per-center leak; a clean return confirms
    the localized identity holds. Slow: a full 365-day, 12-region simulation.
    """
    from main import run_single_simulation

    result = run_single_simulation(
        scenario_name="Baseline",
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.ON_DEMAND,
        seed=123456,
        create_mfa=False,
        raise_on_violation=True,
    )
    assert result["scenario_name"]
