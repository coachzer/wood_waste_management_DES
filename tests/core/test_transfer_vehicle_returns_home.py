"""A transfer delivers at its arrival time and frees its vehicle when it is back home (ADR 0040, 0041).

ADR 0040 sent vehicles home but delivered and freed them on the daily tick, so a vehicle sat idle
up to a day at each end of a trip. ADR 0041 runs both as events, and a freed vehicle takes the next
queued transfer at once. A FAILED collector's vehicles take no new jobs; a trip under way finishes.
"""
import pytest

from config.constants import TRAVEL_SPEED_KMH
from core.collector import CollectorCompany
from models.data_classes import Vehicle
from models.distances import get_distance
from models.enums import EntityStatus

from tests.core.transfer_world import AWAY, HOME, OTHER_WASTE, WASTE, make_world


def _ship(world, waste_type=WASTE, volume=40.0):
    CollectorCompany.transfer_waste_to_region(world.home, waste_type, volume, AWAY)


def test_delivery_happens_at_the_arrival_time_not_the_next_tick():
    world = make_world()
    _ship(world)
    arrival = world.transport_manager.travel_time_days(HOME, AWAY)

    world.env.run(until=arrival - 1e-9)
    assert world.away.collection_center.current_storage[WASTE] == 0.0

    world.env.run(until=arrival + 1e-9)
    assert world.away.collection_center.current_storage[WASTE] == 40.0
    assert world.transport_manager.active_transports == []


def test_the_vehicle_stays_busy_until_it_has_driven_home():
    world = make_world()
    [vehicle] = world.vehicles
    _ship(world)
    back_home_at = 2 * world.transport_manager.travel_time_days(HOME, AWAY)

    world.env.run(until=back_home_at - 1e-9)
    assert vehicle.in_transit and vehicle.current_region == AWAY
    assert world.transport_manager.find_available_vehicle(HOME) is None

    world.env.run(until=back_home_at + 1e-9)
    assert not vehicle.in_transit and vehicle.current_region == HOME


def test_a_vehicle_back_home_takes_the_waiting_transfer_at_once():
    world = make_world()
    _ship(world)
    world.env.run(until=1e-9)
    _ship(world, OTHER_WASTE, 10.0)
    back_home_at = 2 * world.transport_manager.travel_time_days(HOME, AWAY)

    world.env.run(until=back_home_at + 1e-9)

    [transport] = world.transport_manager.active_transports
    assert transport["load_by_type"] == {OTHER_WASTE: 10.0}
    assert transport["pickup_time"] == pytest.approx(back_home_at)


def test_the_return_leg_takes_road_travel_time():
    world = make_world()
    world.transport_manager.road_circuity_mean = 1.35

    assert world.transport_manager.travel_time_days(AWAY, HOME) == pytest.approx(
        get_distance(AWAY, HOME) * 1.35 / TRAVEL_SPEED_KMH / 24.0)


def test_a_failed_collectors_idle_vehicle_takes_no_transfer():
    world = make_world()
    spare = Vehicle(id="away_vehicle", capacity=500.0, current_region=AWAY)
    world.away.vehicles.append(spare)
    world.home.status = EntityStatus.FAILED

    assert world.transport_manager.find_available_vehicle(HOME)["vehicle"] is spare


def test_a_transfer_under_way_when_its_collector_fails_still_delivers_and_the_vehicle_returns_home():
    world = make_world()
    [vehicle] = world.vehicles
    _ship(world)
    world.env.run(until=1e-9)
    world.home.status = EntityStatus.FAILED

    world.env.run(until=30.0)

    assert world.away.collection_center.current_storage[WASTE] == 40.0
    assert not vehicle.in_transit and vehicle.current_region == HOME
    assert world.transport_manager.find_available_vehicle(HOME) is None
