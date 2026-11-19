"""A completed inter-region transfer is charged like a collection trip over road km (ADR 0034, 0038)."""
import pytest
import simpy

from config.constants import (
    COLLECTION_COST_PER_KM_PER_M3,
    KILOGRAMS_PER_TONNE,
    ROAD_CIRCUITY_FACTOR,
    TRANSPORT_EMISSIONS_PER_TON_KM,
    WASTE_DENSITIES,
)
from core.transport_manager import PointToPointTransport
from models.distances import get_distance
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import ChargeRecordingMonitor, make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
TRIP_COST = 50.0


def test_completed_transfer_charges_the_vehicle_owner():
    """Gorenjska queues 40 m3 for Osrednjeslovenska; a Podravska vehicle carries it and pays.

    Neither endpoint has a vehicle, so the bill must follow the vehicle owner, not
    the origin. Mutation check (red): drop the charge in PointToPointTransport.deliver,
    or bill the origin collector.
    """
    env = simpy.Environment()
    monitor = ChargeRecordingMonitor()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)
    origin, destination, owner = (
        make_collector(env, monitor, name=name, region_type=region, state=state,
                       transport_manager=transport_manager, transport_cost=TRIP_COST)
        for name, region in (("col_origin", RegionType.GORENJSKA),
                             ("col_destination", RegionType.OSREDNJESLOVENSKA),
                             ("col_owner", RegionType.PODRAVSKA))
    )
    origin.vehicles = []
    destination.vehicles = []
    state.collectors = [origin, destination, owner]
    origin.collection_center.current_storage[WASTE] = 40.0

    origin.transfer_waste_to_region(WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    env.run(until=1.5)

    distance = get_distance(RegionType.GORENJSKA, RegionType.OSREDNJESLOVENSKA) * ROAD_CIRCUITY_FACTOR
    assert destination.collection_center.current_storage[WASTE] == 40.0
    [(billed_collector, billed_cost)] = monitor.costs
    assert billed_collector == "col_owner"
    fixed_part = billed_cost - distance * COLLECTION_COST_PER_KM_PER_M3 * 40.0
    assert TRIP_COST <= fixed_part < TRIP_COST * 1.01
    tonnes = 40.0 * WASTE_DENSITIES[WASTE] / KILOGRAMS_PER_TONNE
    assert monitor.emissions == [
        ("col_owner", "transport_emissions", pytest.approx(tonnes * distance * TRANSPORT_EMISSIONS_PER_TON_KM)),
    ]
