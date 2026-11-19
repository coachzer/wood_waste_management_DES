"""A PULL collector with no local stock passes a treatment signal upstream once per bus (issue #3).

It used to post once per local PULL generator, so generators sharing the
simulation's single bus received the same signal several times.
"""
from types import SimpleNamespace

import simpy

from config.constants import OPERATING_TICK_DAYS
from models.data_classes import WasteStream
from models.enums import InventoryPolicy, RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import RecordingKanbanManager, make_collector

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _empty_pull_generator(name, kanban_manager):
    return SimpleNamespace(
        name=name,
        region_type=RegionType.PODRAVSKA,
        inventory_policy=InventoryPolicy.PULL,
        kanban_manager=kanban_manager,
        waste_streams={WASTE: WasteStream(waste_type=WASTE, volume=0.0)},
        current_storage=0.0,
    )


def _run_collector_over_treatment_signals(waste_monitor, generator_buses, volume_by_operator):
    """Run a Podravska PULL collector over one same-tick treatment signal per operator."""
    env = simpy.Environment()
    state = SimulationState()
    collector_bus = RecordingKanbanManager()
    state.collectors = [make_collector(
        env, waste_monitor, state=state, inventory_policy=InventoryPolicy.PULL, kanban_manager=collector_bus,
        collection_capacity=1000.0, collection_frequency=1,
    )]
    state.generators = [_empty_pull_generator(f"gen-{index}", bus) for index, bus in enumerate(generator_buses)]
    for operator, volume in volume_by_operator.items():
        collector_bus.add_signal(waste_type=WASTE, timestamp=0.0, volume=volume, source_id=operator,
                                 source_type="treatment", target_region=RegionType.PODRAVSKA)

    env.run(until=1.5 * OPERATING_TICK_DAYS)


def test_generators_sharing_one_bus_get_the_signal_once(ledger_waste_monitor):
    shared_bus = RecordingKanbanManager()

    _run_collector_over_treatment_signals(ledger_waste_monitor, [shared_bus, shared_bus], {"treatment-A": 100.0})

    assert shared_bus.posted_source_types.count("collector") == 1


def test_generators_on_separate_buses_each_get_the_signal(ledger_waste_monitor):
    buses = [RecordingKanbanManager(), RecordingKanbanManager()]

    _run_collector_over_treatment_signals(ledger_waste_monitor, buses, {"treatment-A": 100.0})

    assert [bus.posted_source_types.count("collector") for bus in buses] == [1, 1]


def test_two_operators_same_tick_orders_both_reach_the_generators(ledger_waste_monitor):
    bus = RecordingKanbanManager()

    _run_collector_over_treatment_signals(ledger_waste_monitor, [bus], {"treatment-A": 100.0, "treatment-B": 40.0})

    forwarded = [s["volume"] for s in bus.get_signals() if s["source_type"] == "collector"]
    assert sorted(forwarded) == [40.0, 100.0]
