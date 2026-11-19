"""One vehicle carries every type a collector sends to the same destination in one dispatch (ADR 0041).

One vehicle per request and type saturated the fleet and charged a fixed trip fee per type.
"""
from core.collector import CollectorCompany

from tests.core.transfer_world import AWAY, OTHER_WASTE, THIRD, WASTE, make_world


def test_types_requested_in_the_same_instant_for_one_destination_share_one_vehicle():
    world = make_world(home_vehicles=2)
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 30.0, AWAY)
    CollectorCompany.transfer_waste_to_region(world.home, OTHER_WASTE, 10.0, AWAY)

    world.env.run(until=1e-9)

    [transport] = world.transport_manager.active_transports
    assert transport["load_by_type"] == {WASTE: 30.0, OTHER_WASTE: 10.0}
    assert transport["volume"] == 40.0
    assert sum(vehicle.in_transit for vehicle in world.vehicles) == 1


def test_one_consolidated_trip_pays_one_fixed_fee():
    world = make_world(home_vehicles=2)
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 30.0, AWAY)
    CollectorCompany.transfer_waste_to_region(world.home, OTHER_WASTE, 10.0, AWAY)

    world.env.run(until=30.0)

    assert [load for load, _ in world.home.trips] == [{WASTE: 30.0, OTHER_WASTE: 10.0}]
    assert world.away.collection_center.current_storage == {WASTE: 30.0, OTHER_WASTE: 10.0}


def test_different_destinations_take_different_vehicles():
    world = make_world(home_vehicles=2)
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 30.0, AWAY)
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 10.0, THIRD)

    world.env.run(until=1e-9)

    assert sorted(transport["volume"] for transport in world.transport_manager.active_transports) == [10.0, 30.0]
