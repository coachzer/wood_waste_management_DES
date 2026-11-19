"""A requested transfer's volume leaves the sending center at request time (ADR 0041).

Before ADR 0041 the volume stayed in the center until a vehicle loaded it. A fallback drain in the
same treatment call could then take it, so about 30% of PULL's requested transfer volume was never
loaded. Holding it at request time leaves nothing for another drain to take.
"""
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator

from tests.core.transfer_world import AWAY, WASTE, make_world


def test_the_requested_volume_leaves_the_sending_center_at_request_time():
    world = make_world(home_vehicles=0)

    assert CollectorCompany.transfer_waste_to_region(world.home, WASTE, 40.0, AWAY)

    assert world.home.collection_center.current_storage[WASTE] == 60.0
    assert world.transport_manager.held_volume_by_requester() == {"col_home": 40.0}


def test_a_drain_in_the_same_instant_cannot_take_held_volume():
    world = make_world(home_stock={WASTE: 100.0})
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 40.0, AWAY)
    world.home.collection_center.current_storage[WASTE] = 0.0

    world.env.run(until=1e-9)

    [transport] = world.home.active_transports
    assert transport["load_by_type"] == {WASTE: 40.0}


def test_a_loaded_vehicle_takes_nothing_more_from_the_center():
    world = make_world(home_stock={WASTE: 100.0})
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 40.0, AWAY)

    world.env.run(until=1e-9)

    assert world.home.collection_center.current_storage[WASTE] == 60.0
    assert world.transport_manager.held_volume_by_requester() == {}


def test_a_request_beyond_the_stock_holds_only_the_stock():
    world = make_world(home_stock={WASTE: 15.0}, home_vehicles=0)

    assert world.transport_manager.request_transport(_request(40.0))

    assert world.home.collection_center.current_storage[WASTE] == 0.0
    assert world.transport_manager.held_volume_by_requester() == {"col_home": 15.0}


def test_a_request_with_no_stock_is_refused_and_not_queued():
    world = make_world(home_stock={WASTE: 0.0}, home_vehicles=0)

    assert not world.transport_manager.request_transport(_request(40.0))
    assert world.transport_manager.pending_requests == []


def test_a_new_claim_sees_only_what_held_transfers_left():
    world = make_world(home_stock={WASTE: 100.0}, home_vehicles=0)
    CollectorCompany.transfer_waste_to_region(world.home, WASTE, 70.0, AWAY)

    available = TreatmentOperator._get_available_waste_from_collector(None, world.home, 100.0, [WASTE])

    assert available == {WASTE: 30.0}


def _request(volume):
    from core.transport_manager import TransportRequest
    from tests.core.transfer_world import HOME
    return TransportRequest(origin=HOME, destination=AWAY, waste_type=WASTE, volume=volume,
                            request_time=0.0, requester_id="col_home")
