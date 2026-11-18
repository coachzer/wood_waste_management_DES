"""A queued transfer leaves its volume at the sending center until a vehicle loads it.

Debiting at queue time put waiting volume in no ledger: seed 1 PUSH left about 10k m3 that
neither the collection center nor any vehicle held.
"""
from types import SimpleNamespace

from core.collector import CollectorCompany
from core.transport_manager import PointToPointTransport, TransportRequest
from models.data_classes import Vehicle
from models.enums import RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _world(origin_stock, vehicles):
    origin = SimpleNamespace(
        name="col_origin", region_type=RegionType.GORENJSKA, vehicles=vehicles,
        collection_center=SimpleNamespace(current_storage={WASTE: origin_stock}),
    )
    destination = SimpleNamespace(
        name="col_destination", region_type=RegionType.OSREDNJESLOVENSKA, vehicles=[],
        collection_center=SimpleNamespace(current_storage={WASTE: 0.0}),
    )
    state = SimpleNamespace(collectors=[origin, destination], track_transport_flow=lambda **flow: None)
    transport_manager = PointToPointTransport(state=state)
    origin.transport_manager = transport_manager
    origin.env = SimpleNamespace(now=0.0)
    return origin, transport_manager


def _vehicle():
    return Vehicle(id="v1", capacity=500.0, current_region=RegionType.GORENJSKA)


def test_queued_volume_stays_at_the_sending_center_until_a_vehicle_loads_it():
    vehicle = _vehicle()
    vehicle.in_transit = True
    origin, transport_manager = _world(origin_stock=100.0, vehicles=[vehicle])

    assert CollectorCompany.transfer_waste_to_region(origin, WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    assert transport_manager.process_requests(current_time=0.0) == []
    assert origin.collection_center.current_storage[WASTE] == 100.0

    vehicle.in_transit = False
    [transport] = transport_manager.process_requests(current_time=1.0)
    assert transport["volume"] == 40.0
    assert origin.collection_center.current_storage[WASTE] == 60.0


def test_a_request_whose_stock_left_meanwhile_loads_only_what_remains():
    origin, transport_manager = _world(origin_stock=100.0, vehicles=[_vehicle()])
    CollectorCompany.transfer_waste_to_region(origin, WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    origin.collection_center.current_storage[WASTE] = 15.0

    [transport] = transport_manager.process_requests(current_time=0.0)

    assert transport["volume"] == 15.0
    assert origin.collection_center.current_storage[WASTE] == 0.0


def test_a_request_with_no_stock_left_is_dropped():
    origin, transport_manager = _world(origin_stock=100.0, vehicles=[_vehicle()])
    CollectorCompany.transfer_waste_to_region(origin, WASTE, 40.0, RegionType.OSREDNJESLOVENSKA)
    origin.collection_center.current_storage[WASTE] = 0.0

    assert transport_manager.process_requests(current_time=0.0) == []
    assert transport_manager.pending_requests == []
