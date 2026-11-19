"""Collectors serve treatment signals first, largest first, newest per operator and type (ADR 0031).

A real PULL collector in Gorenjska with one free vehicle reads the bus at its
day-1 tick; what lands in its center shows which order got the vehicle.
"""
import simpy

from models.enums import InventoryPolicy, RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_generator_site

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
BARK = WasteType.BARK_CORK_WASTE_03_01_01
REGION = RegionType.GORENJSKA


def _treatment_signal(kanban_manager, waste_type, volume, timestamp=1.0):
    kanban_manager.add_signal(
        waste_type=waste_type, timestamp=timestamp, volume=volume,
        source_id="proc_gorenjska", source_type="treatment", target_region=REGION,
    )


def _dispatch(waste_monitor, post_signals):
    """Post signals, run the collector's day-1 tick with one free vehicle; return (center stock, bus)."""
    env = simpy.Environment()
    state = SimulationState()
    collector = make_collector(
        env, waste_monitor, state=state, region_type=REGION, inventory_policy=InventoryPolicy.PULL,
        waste_types=[SAWDUST, BARK], collection_capacity=1000.0, collection_frequency=1,
    )
    state.collectors = [collector]
    state.generators = [make_generator_site({SAWDUST: 500.0, BARK: 500.0}, name="gen_gorenjska", region_type=REGION)]
    for vehicle in collector.vehicles[1:]:
        vehicle.in_transit = True
    post_signals(collector.kanban_manager)

    env.run(until=1.5)

    stock = {waste_type: volume for waste_type, volume in collector.collection_center.current_storage.items() if volume}
    return stock, collector.kanban_manager.get_signals(1.0)


def test_largest_treatment_order_gets_the_last_vehicle(ledger_waste_monitor):
    """Mutation check (red): keep signals in posting order."""
    def post(kanban_manager):
        _treatment_signal(kanban_manager, BARK, 0.02)
        _treatment_signal(kanban_manager, SAWDUST, 300.0)

    stock, _ = _dispatch(ledger_waste_monitor, post)

    assert stock == {SAWDUST: 300.0}


def test_treatment_order_beats_a_larger_generator_signal(ledger_waste_monitor):
    """Mutation check (red): sort all signals by volume alone."""
    def post(kanban_manager):
        kanban_manager.add_signal(
            waste_type=BARK, timestamp=1.0, volume=450.0, source_id="gen_gorenjska", source_type="generator",
        )
        _treatment_signal(kanban_manager, SAWDUST, 10.0)

    stock, _ = _dispatch(ledger_waste_monitor, post)

    assert stock == {SAWDUST: 10.0}


def test_only_the_newest_order_per_operator_and_type_is_live(ledger_waste_monitor):
    """Mutation check (red): sum duplicate orders instead of keeping the newest."""
    def post(kanban_manager):
        _treatment_signal(kanban_manager, SAWDUST, 300.0, timestamp=0.5)
        _treatment_signal(kanban_manager, SAWDUST, 120.0)

    stock, bus = _dispatch(ledger_waste_monitor, post)

    assert stock == {SAWDUST: 120.0}
    assert bus == []
