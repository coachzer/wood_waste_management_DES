"""A queued transfer leaves its volume at the sending center until a vehicle loads it.

Debiting at queue time put waiting volume in no ledger: seed 1 PUSH left about 10k m3 that
neither the collection center nor any vehicle held.
"""
import simpy

from core.transport_manager import PointToPointTransport
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_treatment

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _origin(noop_waste_monitor, origin_stock):
    """A Gorenjska collector holding ``origin_stock`` and an Osrednjeslovenska destination."""
    env = simpy.Environment()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0)
    origin, destination = (
        make_collector(env, noop_waste_monitor, name=name, region_type=region,
                       state=state, transport_manager=transport_manager)
        for name, region in (("col_origin", RegionType.GORENJSKA),
                             ("col_destination", RegionType.OSREDNJESLOVENSKA))
    )
    state.collectors = [origin, destination]
    origin.collection_center.current_storage[WASTE] = origin_stock
    return origin, transport_manager


def test_queued_volume_stays_at_the_sending_center_until_a_vehicle_loads_it(noop_waste_monitor):
    origin, transport_manager = _origin(noop_waste_monitor, origin_stock=100.0)
    for collector in transport_manager.state.collectors:
        for vehicle in collector.vehicles:
            vehicle.in_transit = True

    origin.transfer_waste_to_region(WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    assert transport_manager.process_requests(current_time=0.0) == []
    assert origin.collection_center.current_storage[WASTE] == 100.0

    origin.vehicles[0].in_transit = False
    [transport] = transport_manager.process_requests(current_time=1.0)
    assert transport["volume"] == 40.0
    assert origin.collection_center.current_storage[WASTE] == 60.0


def test_a_request_whose_stock_left_meanwhile_loads_only_what_remains(noop_waste_monitor):
    origin, transport_manager = _origin(noop_waste_monitor, origin_stock=100.0)
    origin.transfer_waste_to_region(WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    origin.collection_center.current_storage[WASTE] = 15.0

    [transport] = transport_manager.process_requests(current_time=0.0)

    assert transport["volume"] == 15.0
    assert origin.collection_center.current_storage[WASTE] == 0.0


def test_a_request_with_no_stock_left_is_dropped(noop_waste_monitor):
    origin, transport_manager = _origin(noop_waste_monitor, origin_stock=100.0)
    origin.transfer_waste_to_region(WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    origin.collection_center.current_storage[WASTE] = 0.0

    assert transport_manager.process_requests(current_time=0.0) == []
    assert transport_manager.pending_requests == []


def test_a_new_transfer_cannot_claim_volume_an_earlier_queued_transfer_already_claimed(noop_waste_monitor):
    """Queued volume is still center stock, so a second request would count it again and the
    treatment would treat the order as met while only one vehicle can load it."""
    origin, _ = _origin(noop_waste_monitor, origin_stock=100.0)
    treatment = make_treatment(origin.env, noop_waste_monitor,
                               order_share_by_waste_type={WASTE: 1.0}, order_up_to_level_m3=100.0)

    origin.transfer_waste_to_region(WASTE, 70.0, RegionType.OSREDNJESLOVENSKA)

    assert origin.collection_center.current_storage[WASTE] == 100.0
    assert treatment._get_available_waste_from_collector(origin, 100.0, [WASTE]) == {WASTE: 30.0}
