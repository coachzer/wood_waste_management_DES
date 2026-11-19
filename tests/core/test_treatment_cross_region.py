"""Cross-region repositioning is not counted as collected waste (ADR 0009).

The cross-region share of a request is a collector-to-collector repositioning
move: the remote collector queues a transfer to this region, and treatment picks
the waste up later through the local intake path. Counting it as collected now
would double-count it in the waste-side mass balance.

An operator in Osrednjeslovenska asks for 100 m3 through ``request_waste_directly``:
80% local, 20% cross-region, then a fallback drain for whatever is still missing.
"""
import pytest
import simpy

from core.transport_manager import PointToPointTransport
from models.distances import get_distance
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_treatment

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
HOME = RegionType.OSREDNJESLOVENSKA


def _request_100(waste_monitor, stock_by_region):
    """One collector per region holding the given stock; returns (collected, queued transfers by origin)."""
    env = simpy.Environment()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)
    state.collectors = []
    for region, stock in stock_by_region.items():
        collector = make_collector(
            env, waste_monitor, name=f"col_{region.value}", region_type=region,
            state=state, transport_manager=transport_manager,
        )
        collector.collection_center.current_storage[CONSTRUCTION] = stock
        state.collectors.append(collector)
    operator = make_treatment(
        env, waste_monitor, name="proc_home", region_type=HOME, state=state, transformations={},
        order_share_by_waste_type={CONSTRUCTION: 1.0}, order_up_to_level_m3=100.0,
    )

    collected = operator.request_waste_directly(100.0, [CONSTRUCTION]).collected

    queued = {request.origin: request.volume for request in transport_manager.pending_requests}
    return collected, queued


def test_cross_region_share_is_queued_not_collected(ledger_waste_monitor):
    """The local 80 drains from Podravska by fallback; the 20 cross-region share is only queued.

    Mutation check (red): add the transfer to collected_waste -> 100 collected.
    """
    collected, queued = _request_100(ledger_waste_monitor, {HOME: 0.0, RegionType.PODRAVSKA: 500.0})

    assert queued == {RegionType.PODRAVSKA: pytest.approx(20.0)}
    assert collected == {CONSTRUCTION: pytest.approx(80.0)}


def test_unfilled_cross_region_share_falls_back_to_a_drain(ledger_waste_monitor):
    """The three nearest remote regions can transfer only 5 of the 20, so the fallback
    drains the local 80 plus the missing 15 from far-off Pomurska.

    Pomurska is listed before Gorenjska, so the fallback fills from it and never
    touches the 5 m3 Gorenjska has queued.

    Mutation check (red): return the full request instead of the remainder -> 100 collected.
    """
    collected, queued = _request_100(ledger_waste_monitor, {
        HOME: 0.0, RegionType.POMURSKA: 500.0, RegionType.GORENJSKA: 5.0,
        RegionType.PRIMORSKONOTRANJSKA: 0.0, RegionType.ZASAVSKA: 0.0,
    })

    assert queued == {RegionType.GORENJSKA: 5.0}
    assert collected == {CONSTRUCTION: pytest.approx(95.0)}


def test_cross_region_asks_only_the_three_nearest_remote_collectors(ledger_waste_monitor):
    """Every collector holds 1 m3; transfers come from the three nearest remote regions only."""
    regions = [HOME, RegionType.GORENJSKA, RegionType.GORISKA, RegionType.SAVINJSKA,
               RegionType.PODRAVSKA, RegionType.KOROSKA]
    nearest_three = sorted(regions[1:], key=lambda region: get_distance(HOME, region))[:3]

    _, queued = _request_100(ledger_waste_monitor, {region: 1.0 for region in regions})

    assert set(queued) == set(nearest_three)
