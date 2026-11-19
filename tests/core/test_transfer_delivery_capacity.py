"""A delivered transfer goes through the destination's storage capacity check (ADR 0009)."""
from types import SimpleNamespace

import simpy

from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _deliver(ledger_waste_monitor, load, stock):
    env = simpy.Environment()
    state = SimulationState()
    destination = make_collector(env, ledger_waste_monitor, state=state, name="col-destination")
    destination.collection_center.current_storage[WASTE] = stock
    state.collectors = [destination]
    origin = SimpleNamespace(charge_trip=lambda load, distance: 0.0)
    transport = {
        "collector": origin, "origin": RegionType.GORENJSKA, "destination": destination.region_type,
        "load_by_type": {WASTE: load},
    }
    capacity = destination.waste_storage_capacity
    destination.transport_manager.deliver(transport)
    return destination, capacity


def test_delivery_to_a_nearly_full_center_does_not_exceed_capacity(ledger_waste_monitor):
    destination, capacity = _deliver(ledger_waste_monitor, load=150.0, stock=190.0)

    stored = sum(destination.collection_center.current_storage.values())
    assert stored <= destination.waste_storage_capacity + 1e-9
    landfilled = sum(ledger_waste_monitor.store.landfilled_volume_by_entity().values())
    expanded = destination.waste_storage_capacity - capacity
    assert landfilled > 0 or expanded > 0


def test_every_delivered_m3_is_stored_or_landfilled(ledger_waste_monitor):
    destination, _ = _deliver(ledger_waste_monitor, load=150.0, stock=190.0)

    stored = sum(destination.collection_center.current_storage.values())
    landfilled = sum(ledger_waste_monitor.store.landfilled_volume_by_entity().values())
    assert abs(stored + landfilled - (190.0 + 150.0)) < 1e-9


def test_delivery_that_fits_is_stored_in_full_and_not_counted_as_collected(ledger_waste_monitor):
    destination, _ = _deliver(ledger_waste_monitor, load=50.0, stock=0.0)

    assert destination.collection_center.current_storage[WASTE] == 50.0
    assert destination.collected_waste[WASTE] == 0.0
