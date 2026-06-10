"""Treatment-echelon inbound flow is collector intake, not the reposition log (ADR 0009).

These tests pin the corrected waste-side flow accounting from issue 11:

- ``CollectorCompany.provide_waste_for_treatment`` -- the real intake that
  decrements collector storage and feeds the treatment process -- must log a
  ``collector -> treatment`` transport flow, so the bullwhip Treatment echelon
  reads real replenishment.
- ``PointToPointTransport._create_transport`` -- the cross-region repositioning
  move -- must log ``collector -> collector`` (an intra-Collector-echelon move),
  not ``collector -> treatment``, so the net-zero reposition no longer pollutes
  the Treatment echelon.

Methods are driven as unbound functions over lightweight stand-in ``self``
objects exposing exactly what each reads -- no SimPy clock or full entity
construction (matches the house test style).
"""

from types import SimpleNamespace

from core.collector import CollectorCompany
from core.transport_manager import (
    PointToPointTransport,
    TransportRequest,
)
from models.enums import RegionType, WasteType
from models.state import SimulationState


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03


def make_intake_collector(storage, state, name="collector-1"):
    """A collector stand-in exposing what provide_waste_for_treatment reads."""
    return SimpleNamespace(
        name=name,
        collection_center=SimpleNamespace(current_storage=dict(storage)),
        state=state,
        env=SimpleNamespace(now=12.0),
    )


def treatment_flows(state):
    return [f for f in state.transport_flows if f["target_type"] == "treatment"]


def test_intake_logs_collector_to_treatment_flow():
    """Each waste type handed to treatment is logged as a collector->treatment
    flow carrying the transferred volume."""
    state = SimulationState()
    collector = make_intake_collector({CONSTRUCTION: 100.0, PACKAGING: 40.0}, state)

    provided = CollectorCompany.provide_waste_for_treatment(
        collector, 70.0, [CONSTRUCTION, PACKAGING], treatment_name="treatment-1"
    )

    # 70 requested: 100 available of CONSTRUCTION covers it entirely.
    assert provided[CONSTRUCTION] == 70.0
    assert PACKAGING not in provided

    flows = treatment_flows(state)
    assert len(flows) == 1
    flow = flows[0]
    assert flow["source_type"] == "collector"
    assert flow["source_name"] == "collector-1"
    assert flow["target_name"] == "treatment-1"
    assert flow["waste_type"] == CONSTRUCTION.value
    assert flow["volume"] == 70.0


def test_intake_logs_one_flow_per_waste_type():
    """Drawing across two waste types logs one flow each, with the per-type volume."""
    state = SimulationState()
    collector = make_intake_collector({CONSTRUCTION: 30.0, PACKAGING: 50.0}, state)

    provided = CollectorCompany.provide_waste_for_treatment(
        collector, 60.0, [CONSTRUCTION, PACKAGING], treatment_name="treatment-1"
    )

    assert provided[CONSTRUCTION] == 30.0
    assert provided[PACKAGING] == 30.0

    flows = treatment_flows(state)
    volumes = {f["waste_type"]: f["volume"] for f in flows}
    assert volumes == {CONSTRUCTION.value: 30.0, PACKAGING.value: 30.0}


def make_transport_manager(state):
    """A PointToPointTransport stand-in: _create_transport reads only self.state."""
    return SimpleNamespace(state=state)


def test_reposition_logs_collector_to_collector_not_treatment():
    """The cross-region repositioning move is intra-Collector-echelon physical
    movement (ADR 0009): it logs collector->collector with the destination-region
    collector as target, and the Treatment echelon never sees it."""
    origin, destination = RegionType.OSREDNJESLOVENSKA, RegionType.PODRAVSKA
    state = SimulationState()
    destination_collector = SimpleNamespace(name="collector-dest", region_type=destination)
    state.collectors = [destination_collector]
    # A treatment operator sits in the destination region too -- the old code
    # would have mislabeled the flow onto it; the relabel must ignore it.
    state.treatment_operators = [SimpleNamespace(name="treatment-dest", region_type=destination)]

    vehicle = SimpleNamespace(
        in_transit=False, destination=None, estimated_arrival=None,
        current_load=0.0, current_region=origin,
    )
    vehicle_info = {"vehicle": vehicle, "collector": SimpleNamespace(name="collector-src")}
    request = TransportRequest(
        origin=origin, destination=destination, waste_type=CONSTRUCTION,
        volume=120.0, request_time=0.0,
        requester_id="collector-src",
    )

    PointToPointTransport._create_transport(
        make_transport_manager(state), request, vehicle_info, current_time=5.0
    )

    assert treatment_flows(state) == []
    assert len(state.transport_flows) == 1
    flow = state.transport_flows[0]
    assert flow["source_type"] == "collector"
    assert flow["source_name"] == "collector-src"
    assert flow["target_type"] == "collector"
    assert flow["target_name"] == "collector-dest"
    assert flow["volume"] == 120.0


def test_reposition_logs_origin_collector_not_borrowed_vehicle_owner():
    """The reposition source is the ORIGIN collector, not the carrier.

    When the origin collector's own vehicles are busy, ``find_available_vehicle``
    borrows a neighbouring collector's vehicle. The mass leaves the origin
    collector's storage (``transfer_waste_to_region`` decremented it), so the
    flow's ``source_name`` must be the origin collector -- identified by
    ``request.requester_id`` -- not the borrowed vehicle's owner. Sourcing it on
    the carrier mis-attributes the outflow and breaks the per-collection-center
    mass-balance identity (``check_collection_centers``)."""
    origin, destination = RegionType.KOROSKA, RegionType.PODRAVSKA
    state = SimulationState()
    state.collectors = [
        SimpleNamespace(name="col-origin", region_type=origin),
        SimpleNamespace(name="col-dest", region_type=destination),
    ]

    # The only available vehicle belongs to a DIFFERENT collector (borrowed).
    vehicle = SimpleNamespace(
        in_transit=False, destination=None, estimated_arrival=None,
        current_load=0.0, current_region=origin,
    )
    vehicle_info = {"vehicle": vehicle, "collector": SimpleNamespace(name="col-vehicle-owner")}
    request = TransportRequest(
        origin=origin, destination=destination, waste_type=CONSTRUCTION,
        volume=120.0, request_time=0.0,
        requester_id="col-origin",
    )

    PointToPointTransport._create_transport(
        make_transport_manager(state), request, vehicle_info, current_time=5.0
    )

    flow = state.transport_flows[0]
    assert flow["source_name"] == "col-origin"
    assert flow["target_name"] == "col-dest"
