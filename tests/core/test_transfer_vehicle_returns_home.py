"""A transfer vehicle drives home empty after delivering, and a FAILED collector's vehicles take no new jobs.

Before this, a vehicle stayed wherever it delivered and the next transfer picked the nearest idle
vehicle from any region, so vehicles drifted away from home and failed collectors kept hauling.

Real collectors in Gorenjska (home) and Osrednjeslovenska (away) share one transport manager and
run its daily tick. Road circuity is stretched so each leg takes 1.5 days: the transfer leaves
at day 0, is delivered at the day-2 tick (arrival 1.5) and the vehicle is home by the day-3 tick
(back at 3.0).
"""
import pytest
import simpy

from config.constants import TRAVEL_SPEED_KMH
from core.transport_manager import PointToPointTransport
from models.distances import get_distance
from models.enums import EntityStatus, RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
HOME = RegionType.GORENJSKA
AWAY = RegionType.OSREDNJESLOVENSKA
LEG_DAYS = 1.5


def _world(waste_monitor):
    """Home holds 100 m3 and queues a 40 m3 transfer to away."""
    env = simpy.Environment()
    state = SimulationState()
    great_circle_days = get_distance(HOME, AWAY) / TRAVEL_SPEED_KMH / 24.0
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=LEG_DAYS / great_circle_days)
    home, away = (
        make_collector(env, waste_monitor, name=name, region_type=region, state=state,
                       transport_manager=transport_manager)
        for name, region in (("col_home", HOME), ("col_away", AWAY))
    )
    state.collectors = [home, away]
    home.collection_center.current_storage[WASTE] = 100.0
    home.transfer_waste_to_region(WASTE, 40.0, AWAY)
    assert transport_manager.travel_time_days(HOME, AWAY) == pytest.approx(LEG_DAYS)
    return env, home, away


def _busy(collector):
    return [vehicle for vehicle in collector.vehicles if vehicle.in_transit]


def test_a_vehicle_that_delivered_elsewhere_stays_busy_until_it_has_driven_home(ledger_waste_monitor):
    env, home, away = _world(ledger_waste_monitor)

    env.run(until=2.5)
    assert away.collection_center.current_storage[WASTE] == 40.0
    [vehicle] = _busy(home)
    assert vehicle.current_region == AWAY

    env.run(until=3.5)
    assert not vehicle.in_transit
    assert vehicle.current_region == HOME


def test_a_failed_collectors_idle_vehicle_takes_no_transfer(ledger_waste_monitor):
    env, home, away = _world(ledger_waste_monitor)
    home.status = EntityStatus.FAILED

    env.run(until=0.5)

    assert _busy(home) == []
    assert len(_busy(away)) == 1


def test_a_transfer_under_way_when_its_collector_fails_still_delivers_and_the_vehicle_returns_home(
    ledger_waste_monitor,
):
    env, home, away = _world(ledger_waste_monitor)
    env.run(until=0.5)
    [vehicle] = _busy(home)
    home.status = EntityStatus.FAILED

    env.run(until=10.5)

    assert away.collection_center.current_storage[WASTE] == 40.0
    assert not vehicle.in_transit and vehicle.current_region == HOME
