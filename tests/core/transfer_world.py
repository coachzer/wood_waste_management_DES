"""A minimal two-region world for inter-region transfer tests."""
from types import SimpleNamespace

import simpy

from core.transport_manager import PointToPointTransport
from models.data_classes import Vehicle
from models.enums import EntityStatus, RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
OTHER_WASTE = WasteType.WOODEN_PACKAGING_15_01_03
HOME = RegionType.GORENJSKA
AWAY = RegionType.OSREDNJESLOVENSKA
THIRD = RegionType.PODRAVSKA


def make_collector(name, region_type, vehicles=(), stock=None):
    collector = SimpleNamespace(
        name=name, region_type=region_type, vehicles=list(vehicles), status=EntityStatus.OPERATIONAL,
        collection_center=SimpleNamespace(current_storage=dict({WASTE: 0.0, OTHER_WASTE: 0.0} if stock is None else stock)),
        trips=[],
    )
    collector.charge_trip = lambda load, distance: collector.trips.append((dict(load), distance))
    return collector


def make_world(home_stock=None, home_vehicles=1):
    vehicles = [Vehicle(id=f"home_vehicle_{i}", capacity=500.0, current_region=HOME) for i in range(home_vehicles)]
    home = make_collector("col_home", HOME, vehicles, {WASTE: 100.0, OTHER_WASTE: 100.0} if home_stock is None else home_stock)
    away = make_collector("col_away", AWAY)
    third = make_collector("col_third", THIRD)
    state = SimpleNamespace(collectors=[home, away, third], track_transport_flow=lambda **flow: None)
    env = simpy.Environment()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)
    for collector in (home, away, third):
        collector.state = state
        collector.transport_manager = transport_manager
        collector.env = env
    return SimpleNamespace(env=env, home=home, away=away, third=third, vehicles=vehicles,
                           transport_manager=transport_manager)
