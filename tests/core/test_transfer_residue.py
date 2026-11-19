"""A delivered transfer under RESIDUE_TRANSFER_VOLUME_M3 is still charged and is recorded (float residue)."""
import simpy

from config.constants import RESIDUE_TRANSFER_VOLUME_M3
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _deliver(ledger_waste_monitor, load):
    env = simpy.Environment()
    state = SimulationState()
    origin = make_collector(env, ledger_waste_monitor, state=state, name="col-origin")
    destination = make_collector(env, ledger_waste_monitor, state=state, name="col-destination",
                                 region_type=RegionType.GORENJSKA)
    state.collectors = [origin, destination]
    origin.transport_manager.deliver({
        "collector": origin, "origin": origin.region_type, "destination": destination.region_type,
        "load_by_type": {WASTE: load}, "requester_id": origin.name,
    })
    return state, origin


def test_a_residue_transfer_is_recorded_with_the_trip_cost_it_paid(ledger_waste_monitor):
    state, origin = _deliver(ledger_waste_monitor, RESIDUE_TRANSFER_VOLUME_M3 / 10)

    [transfer] = state.residue_transfers
    assert transfer["source_name"] == "col-origin"
    assert transfer["cost"] >= origin.transport_cost


def test_a_real_transfer_is_not_recorded_as_residue(ledger_waste_monitor):
    state, _ = _deliver(ledger_waste_monitor, 5.0)

    assert state.residue_transfers == []
