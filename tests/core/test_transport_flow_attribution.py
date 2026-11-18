"""Repositioning flows are attributed to the origin collector, not the vehicle's owner.

find_available_vehicle may borrow a vehicle from another region's collector. The origin
collector is the one whose storage the transfer drew down, so the flow log must name it,
or per-collection-center flow identities break.
"""
from types import SimpleNamespace

from core.transport_manager import PointToPointTransport, TransportRequest
from models.data_classes import Vehicle
from models.enums import RegionType, WasteType


def _collector(name, region_type, vehicles, stock=0.0):
    return SimpleNamespace(
        name=name, region_type=region_type, vehicles=vehicles,
        collection_center=SimpleNamespace(current_storage={WasteType.CONSTRUCTION_WOOD_17_02_01: stock}),
    )


def test_flow_from_a_borrowed_vehicle_names_the_origin_collector():
    flows = []
    origin = _collector("col_origin", RegionType.GORENJSKA, [], stock=10.0)
    lender = _collector(
        "col_lender", RegionType.PODRAVSKA,
        [Vehicle(id="v1", capacity=50.0, current_region=RegionType.PODRAVSKA)],
    )
    destination = _collector("col_destination", RegionType.OSREDNJESLOVENSKA, [])
    state = SimpleNamespace(
        collectors=[origin, lender, destination],
        track_transport_flow=lambda **flow: flows.append(flow),
    )
    transport_manager = PointToPointTransport(state=state)
    transport_manager.request_transport(TransportRequest(
        origin=RegionType.GORENJSKA, destination=RegionType.OSREDNJESLOVENSKA,
        waste_type=WasteType.CONSTRUCTION_WOOD_17_02_01, volume=10.0,
        request_time=0.0, requester_id="col_origin",
    ))

    [transport] = transport_manager.process_requests(current_time=0.0)

    assert transport["collector"] is lender
    assert [(flow["source_name"], flow["target_name"]) for flow in flows] == [("col_origin", "col_destination")]
