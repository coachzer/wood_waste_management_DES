"""A fallback drain from another region is charged as a loaded trip; a local drain is not (ADR 0037, 0042)."""
import pytest
import simpy

from config.constants import COLLECTION_COST_PER_KM_PER_M3, ROAD_CIRCUITY_FACTOR
from core.transport_manager import PointToPointTransport
from models.distances import get_distance
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import ChargeRecordingMonitor, make_collector, make_treatment

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
HOME = RegionType.OSREDNJESLOVENSKA
REMOTE = RegionType.GORENJSKA


def test_only_the_remote_drain_is_charged_over_its_distance():
    """An operator asks for 100 m3; its local collector holds 30, a Gorenjska one holds 500.

    The local 80% share drains the 30 free of charge, the cross-region 20% is queued
    as a transfer, and the fallback drains the missing 50 from Gorenjska as one
    charged trip.

    Mutation check (red): skip the charge, or charge local drains too.
    """
    env = simpy.Environment()
    monitor = ChargeRecordingMonitor()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)
    local, remote = (
        make_collector(env, monitor, name=name, region_type=region, state=state, transport_manager=transport_manager)
        for name, region in (("col_home", HOME), ("col_remote", REMOTE))
    )
    state.collectors = [local, remote]
    local.collection_center.current_storage[WASTE] = 30.0
    remote.collection_center.current_storage[WASTE] = 500.0
    operator = make_treatment(
        env, monitor, name="proc_home", region_type=HOME, state=state, transformations={},
        order_share_by_waste_type={WASTE: 1.0}, order_up_to_level_m3=100.0,
    )

    _stored, collected = operator.trigger_collection({WASTE: 100.0})

    assert collected == pytest.approx(80.0)
    road_distance = get_distance(REMOTE, HOME) * ROAD_CIRCUITY_FACTOR
    assert monitor.costs == [
        ("col_remote", pytest.approx(remote.transport_cost + road_distance * COLLECTION_COST_PER_KM_PER_M3 * 50.0)),
    ]
