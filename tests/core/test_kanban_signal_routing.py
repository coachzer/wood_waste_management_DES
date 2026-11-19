"""Tests for treatment kanban signal region routing (plan 008 / ADR 0018).

Treatment signals carry a target_region so that only the collector in the
operator's own region reads and acknowledges them.  Every other PULL collector
on the shared bus must skip them and leave them for the intended recipient.
Signals without a target_region (generator-sourced) pass through any region, and a
collector that cannot serve one leaves it on the bus for one that can.

Collectors are real PULL collectors sharing one bus; each reads it on its own tick.
Pomurska lists Podravska among its closest regions, so it can serve a Podravska
generator; Gorenjska does not, so it cannot.
"""
import simpy

from core.kanban_manager import KanbanManager
from models.enums import InventoryPolicy, RegionType, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_generator_site

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
GENERATOR_STOCK_M3 = 50.0


def _run(waste_monitor, collector_regions, generator_regions=(), post_signal=None):
    """Real PULL collectors on one bus, run past their day-1 tick. Returns (bus, generators by name)."""
    env = simpy.Environment()
    state = SimulationState()
    kanban_manager = KanbanManager()
    state.collectors = [
        make_collector(
            env, waste_monitor, state=state, name=f"collector-{region.value}", region_type=region,
            inventory_policy=InventoryPolicy.PULL, kanban_manager=kanban_manager,
            collection_capacity=1000.0, collection_frequency=1,
        )
        for region in collector_regions
    ]
    state.generators = [
        make_generator_site({WASTE: GENERATOR_STOCK_M3}, name=f"gen-{index}", region_type=region)
        for index, region in enumerate(generator_regions, start=1)
    ]
    post_signal(kanban_manager)

    env.run(until=1.5)

    pending = [signal for signal in kanban_manager.get_signals(1.0) if signal.get("source_type") != "market"]
    return pending, {generator.name: generator for generator in state.generators}


def _treatment_signal_to_podravska(kanban_manager):
    kanban_manager.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                              source_id="treatment-A", source_type="treatment",
                              target_region=RegionType.PODRAVSKA)


def _generator_signal(kanban_manager):
    kanban_manager.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                              source_id="gen-1", source_type="generator")


def test_wrong_region_collector_does_not_consume_treatment_signal(ledger_waste_monitor):
    pending, _ = _run(ledger_waste_monitor, [RegionType.GORENJSKA], post_signal=_treatment_signal_to_podravska)

    assert len(pending) == 1, "wrong-region collector must leave the signal on the bus"


def test_right_region_collector_consumes_treatment_signal(ledger_waste_monitor):
    pending, _ = _run(ledger_waste_monitor, [RegionType.PODRAVSKA], post_signal=_treatment_signal_to_podravska)

    assert pending == [], "right-region collector should propagate upstream and ack"


def test_unaddressed_signal_reaches_a_collector_in_another_region(ledger_waste_monitor):
    pending, generators = _run(
        ledger_waste_monitor, [RegionType.POMURSKA], [RegionType.PODRAVSKA], post_signal=_generator_signal,
    )

    assert generators["gen-1"].waste_streams[WASTE].volume < GENERATOR_STOCK_M3
    assert pending == []


def test_collector_that_cannot_serve_a_generator_signal_leaves_it_on_the_bus(ledger_waste_monitor):
    pending, generators = _run(
        ledger_waste_monitor, [RegionType.GORENJSKA], [RegionType.PODRAVSKA], post_signal=_generator_signal,
    )

    assert generators["gen-1"].waste_streams[WASTE].volume == GENERATOR_STOCK_M3
    assert len(pending) == 1


def test_generator_signal_left_by_a_remote_collector_is_served_by_the_local_one(ledger_waste_monitor):
    pending, generators = _run(
        ledger_waste_monitor, [RegionType.GORENJSKA, RegionType.PODRAVSKA], [RegionType.PODRAVSKA],
        post_signal=_generator_signal,
    )

    assert generators["gen-1"].waste_streams[WASTE].volume < GENERATOR_STOCK_M3
    assert pending == []
