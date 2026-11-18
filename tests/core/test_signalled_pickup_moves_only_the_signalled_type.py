"""A kanban signal moves only the waste type it names (ADR 0028)."""
from types import SimpleNamespace

import simpy

from core.collector import CollectorCompany
from models.data_classes import WasteStream
from models.enums import InventoryPolicy, StockStrategy, WasteType
from models.state import SimulationState

FIRST_IN_DICT = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
SIGNALLED = WasteType.CONSTRUCTION_WOOD_17_02_01


def _collector(noop_waste_monitor):
    collector = CollectorCompany(
        env=simpy.Environment(),
        name="collector-1",
        waste_types=[FIRST_IN_DICT, SIGNALLED],
        collection_capacity=1_000.0,
        collection_frequency=12,
        transport_cost=10.0,
        efficiency=1.0,
        region="podravska",
        waste_monitor=noop_waste_monitor,
        inventory_policy=InventoryPolicy.PULL,
        stock_strategy=StockStrategy.REORDER_50,
        state=SimulationState(),
    )
    collector.collection_capacity_per_tick_m3 = 1_000.0
    return collector


def _generator():
    return SimpleNamespace(
        name="generator-1",
        waste_streams={
            FIRST_IN_DICT: WasteStream(waste_type=FIRST_IN_DICT, volume=500.0),
            SIGNALLED: WasteStream(waste_type=SIGNALLED, volume=500.0),
        },
        current_storage=1_000.0,
    )


def test_signalled_pickup_takes_only_the_signalled_type(noop_waste_monitor):
    collector, generator = _collector(noop_waste_monitor), _generator()

    collected, by_type = collector._perform_collection_at_site(generator, target_volume=300.0, waste_type=SIGNALLED)

    assert by_type == {SIGNALLED: 300.0}
    assert generator.waste_streams[FIRST_IN_DICT].volume == 500.0


def test_unsignalled_pickup_still_takes_any_stream(noop_waste_monitor):
    collector, generator = _collector(noop_waste_monitor), _generator()

    collected, by_type = collector._perform_collection_at_site(generator, target_volume=800.0)

    assert collected == 800.0
    assert set(by_type) == {FIRST_IN_DICT, SIGNALLED}
