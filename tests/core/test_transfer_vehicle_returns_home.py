"""A transfer vehicle drives home empty after delivering, and a FAILED collector's vehicles take no new jobs.

Before this, a vehicle stayed wherever it delivered and the next transfer picked the nearest idle
vehicle from any region, so vehicles drifted away from home and failed collectors kept hauling.
"""
from types import SimpleNamespace

import pytest

from config.constants import TRAVEL_SPEED_KMH
from core.collector import CollectorCompany
from core.transport_manager import PointToPointTransport, TransportRequest
from models.data_classes import Vehicle
from models.distances import get_distance
from models.enums import EntityStatus, RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
HOME = RegionType.GORENJSKA
AWAY = RegionType.OSREDNJESLOVENSKA


def _collector(name, region_type, vehicles, stock=0.0):
    collector = SimpleNamespace(
        name=name, region_type=region_type, vehicles=vehicles, status=EntityStatus.OPERATIONAL,
        collection_center=SimpleNamespace(current_storage={WASTE: stock}),
        active_transports=[], returning_vehicles=[],
    )
    collector._record_trip_cost_and_emissions = lambda load, distance: None
    return collector


def _world(away_vehicles=()):
    vehicle = Vehicle(id="home_vehicle", capacity=500.0, current_region=HOME)
    home = _collector("col_home", HOME, [vehicle], stock=100.0)
    away = _collector("col_away", AWAY, list(away_vehicles))
    state = SimpleNamespace(collectors=[home, away], track_transport_flow=lambda **flow: None)
    transport_manager = PointToPointTransport(state=state)
    for collector in (home, away):
        collector.state = state
        collector.transport_manager = transport_manager
    return home, away, vehicle, transport_manager


def _ship(home, transport_manager, current_time=0.0):
    transport_manager.request_transport(TransportRequest(
        origin=HOME, destination=AWAY, waste_type=WASTE, volume=40.0,
        request_time=current_time, requester_id=home.name))
    [transport] = transport_manager.process_requests(current_time)
    home.active_transports.append(transport)
    return transport


def _deliver(collector, current_time):
    completed = CollectorCompany._check_completed_transports(collector, current_time)
    for transport in completed:
        CollectorCompany._handle_completed_transport(collector, transport)
        collector.active_transports.remove(transport)
    return completed


def test_a_vehicle_that_delivered_elsewhere_stays_busy_until_it_has_driven_home():
    home, away, vehicle, transport_manager = _world()
    transport = _ship(home, transport_manager)
    return_days = transport_manager.travel_time_days(AWAY, HOME)
    back_home_at = transport["arrival_time"] + return_days

    assert _deliver(home, transport["arrival_time"]) == [transport]
    assert away.collection_center.current_storage[WASTE] == 40.0
    assert vehicle.in_transit and vehicle.current_region == AWAY
    assert transport_manager.find_available_vehicle(HOME) is None

    _deliver(home, back_home_at - 1e-9)
    assert vehicle.in_transit

    _deliver(home, back_home_at)
    assert not vehicle.in_transit
    assert vehicle.current_region == HOME
    assert transport_manager.find_available_vehicle(HOME)["vehicle"] is vehicle


def test_the_return_leg_takes_road_travel_time():
    _, _, _, transport_manager = _world()
    transport_manager.uncertainty_set = SimpleNamespace(transportation_time=(1.35, 0.1))

    assert transport_manager.travel_time_days(AWAY, HOME) == pytest.approx(
        get_distance(AWAY, HOME) * 1.35 / TRAVEL_SPEED_KMH / 24.0)
    assert transport_manager.travel_time_days(AWAY, HOME) > 0


def test_a_failed_collectors_idle_vehicle_takes_no_transfer():
    spare = Vehicle(id="away_vehicle", capacity=500.0, current_region=AWAY)
    home, _, vehicle, transport_manager = _world(away_vehicles=[spare])
    home.status = EntityStatus.FAILED

    assert transport_manager.find_available_vehicle(HOME)["vehicle"] is spare


def test_a_transfer_under_way_when_its_collector_fails_still_delivers_and_the_vehicle_returns_home():
    home, away, vehicle, transport_manager = _world()
    transport = _ship(home, transport_manager)
    home.status = EntityStatus.FAILED
    long_after = transport["arrival_time"] + 10 * transport_manager.travel_time_days(AWAY, HOME) + 1.0

    _deliver(home, long_after)

    assert away.collection_center.current_storage[WASTE] == 40.0
    assert not vehicle.in_transit and vehicle.current_region == HOME
    assert transport_manager.find_available_vehicle(HOME) is None
