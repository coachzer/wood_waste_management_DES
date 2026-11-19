"""Treatment-echelon inbound flow is collector intake, not the reposition log (ADR 0009).

These tests pin the corrected waste-side flow accounting from issue 11:

- ``CollectorCompany.provide_waste_for_treatment`` -- the real intake that
  decrements collector storage and feeds the treatment process -- must log a
  ``collector -> treatment`` transport flow, so the bullwhip Treatment echelon
  reads real replenishment.
- a processed ``PointToPointTransport`` request -- the cross-region repositioning
  move -- must log ``collector -> collector`` (an intra-Collector-echelon move),
  not ``collector -> treatment``, so the net-zero reposition no longer pollutes
  the Treatment echelon.

Intake runs on a real collector; repositioning runs through a real transport
manager whose collectors are stand-ins exposing what it reads.
"""

from types import SimpleNamespace

import simpy

from core.transport_manager import (
    PointToPointTransport,
    TransportRequest,
)
from models.data_classes import Vehicle
from models.enums import EntityStatus, RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03


def make_intake_collector(storage, state, waste_monitor):
    """A real collector holding ``storage`` in its collection center."""
    collector = make_collector(simpy.Environment(), waste_monitor, waste_types=list(storage), state=state)
    collector.collection_center.current_storage.update(storage)
    return collector


def treatment_flows(state):
    return [f for f in state.transport_flows if f["target_type"] == "treatment"]


def test_intake_logs_collector_to_treatment_flow(noop_waste_monitor):
    """Each waste type handed to treatment is logged as a collector->treatment
    flow carrying the transferred volume."""
    state = SimulationState()
    collector = make_intake_collector({CONSTRUCTION: 100.0, PACKAGING: 40.0}, state, noop_waste_monitor)

    provided = collector.provide_waste_for_treatment(
        70.0, [CONSTRUCTION, PACKAGING], treatment_name="treatment-1"
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


def test_intake_logs_one_flow_per_waste_type(noop_waste_monitor):
    """Drawing across two waste types logs one flow each, with the per-type volume."""
    state = SimulationState()
    collector = make_intake_collector({CONSTRUCTION: 30.0, PACKAGING: 50.0}, state, noop_waste_monitor)

    provided = collector.provide_waste_for_treatment(
        60.0, [CONSTRUCTION, PACKAGING], treatment_name="treatment-1"
    )

    assert provided[CONSTRUCTION] == 30.0
    assert provided[PACKAGING] == 30.0

    flows = treatment_flows(state)
    volumes = {f["waste_type"]: f["volume"] for f in flows}
    assert volumes == {CONSTRUCTION.value: 30.0, PACKAGING.value: 30.0}


def test_reposition_logs_collector_to_collector_not_treatment():
    """The cross-region repositioning move is intra-Collector-echelon physical
    movement (ADR 0009): it logs collector->collector with the destination-region
    collector as target, and the Treatment echelon never sees it."""
    origin, destination = RegionType.OSREDNJESLOVENSKA, RegionType.PODRAVSKA
    state = SimulationState()
    source_collector = SimpleNamespace(
        name="collector-src", region_type=origin, status=EntityStatus.OPERATIONAL,
        vehicles=[Vehicle(id="v1", capacity=500.0, current_region=origin)],
        collection_center=SimpleNamespace(current_storage={CONSTRUCTION: 120.0}),
    )
    destination_collector = SimpleNamespace(
        name="collector-dest", region_type=destination, status=EntityStatus.OPERATIONAL,
        vehicles=[], collection_center=SimpleNamespace(current_storage={CONSTRUCTION: 0.0}),
    )
    state.collectors = [source_collector, destination_collector]
    # A treatment operator sits in the destination region too -- the old code
    # would have mislabeled the flow onto it; the relabel must ignore it.
    state.treatment_operators = [SimpleNamespace(name="treatment-dest", region_type=destination)]
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=simpy.Environment())

    transport_manager.request_transport(TransportRequest(
        origin=origin, destination=destination, waste_type=CONSTRUCTION,
        volume=120.0, request_time=0.0, requester_id="collector-src",
    ))
    transport_manager.process_requests(current_time=5.0)

    assert treatment_flows(state) == []
    assert len(state.transport_flows) == 1
    flow = state.transport_flows[0]
    assert flow["source_type"] == "collector"
    assert flow["source_name"] == "collector-src"
    assert flow["target_type"] == "collector"
    assert flow["target_name"] == "collector-dest"
    assert flow["volume"] == 120.0

