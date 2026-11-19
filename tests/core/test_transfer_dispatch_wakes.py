"""A held transfer leaves as soon as a vehicle can take it, not at the next daily poll (ADR 0041)."""
from types import SimpleNamespace

import simpy

from core.transport_manager import PointToPointTransport
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_generator_site

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
AWAY = RegionType.GORENJSKA


def _world(waste_monitor):
    env = simpy.Environment()
    state = SimulationState()
    transport_manager = PointToPointTransport(state=state, road_circuity_mean=1.0, env=env)
    collector = make_collector(env, waste_monitor, state=state, transport_manager=transport_manager,
                               collection_capacity=10_000.0)
    collector.collection_center.current_storage[WASTE] = 100.0
    destination = SimpleNamespace(name="col_away", region_type=AWAY, vehicles=[], status=collector.status,
                                  collection_center=SimpleNamespace(current_storage={WASTE: 0.0}))
    state.collectors = [collector, destination]
    return env, collector, transport_manager


def test_a_vehicle_back_from_a_pickup_takes_the_held_transfer(ledger_waste_monitor):
    """Mutation check (red): drop the dispatch wake-up when a collection trip ends -> still held."""
    env, collector, transport_manager = _world(ledger_waste_monitor)
    for vehicle in collector.vehicles[1:]:
        vehicle.in_transit = True
    collector.collect_from_generator(make_generator_site({WASTE: 5.0}))
    collector.transfer_waste_to_region(WASTE, 40.0, AWAY)

    env.run(until=0.9)

    assert transport_manager.held_volume_by_requester() == {}


def test_a_collector_leaving_failed_dispatches_its_held_transfer(ledger_waste_monitor):
    """Mutation check (red): drop the dispatch wake-up when a collector leaves FAILED -> still held."""
    env, collector, transport_manager = _world(ledger_waste_monitor)
    collector.transfer_waste_to_region(WASTE, 40.0, AWAY)
    collector.status = collector.status.FAILED
    collector.failure_start_time, collector.downtime_duration = 0.0, 0.5
    collector.failure_config = SimpleNamespace(min_duration=1.0, max_duration=1.0)

    def recover_mid_day():
        yield env.timeout(0.5)
        collector.check_failure(env.now, failure_probability=0.0)

    env.process(recover_mid_day())
    env.run(until=0.9)

    assert transport_manager.held_volume_by_requester() == {}
