"""Shared builders for core tests."""
import json
from types import SimpleNamespace

import simpy

from config.base_config import ScenarioConfig
from config.constants import OPERATING_TICK_DAYS
from core.abc_analysis import abc_priority_weights
from core.collector import CollectorCompany
from core.generator import WasteGenerator
from core.kanban_manager import KanbanManager
from core.transport_manager import PointToPointTransport
from core.treatment import TreatmentOperator
from models.data_classes import WasteStream
from models.enums import EntityStatus, InventoryPolicy, OutputType, RegionType, StockStrategy, WasteType, sorted_by_value
from models.state import SimulationState
from models.transformations import build_transformations

with open("data/demand.json") as demand_file:
    SHIPPED_ABC_PRIORITY_WEIGHTS = abc_priority_weights(json.load(demand_file)["national_demand"])


def deterministic_scenario(**overrides) -> ScenarioConfig:
    """A scenario whose draws are all exact: unit generation factor, catalogue
    conversion efficiency, great-circle (1.0) road circuity, no failures."""
    fields = dict(
        name="Deterministic",
        waste_generation_mean=1.0,
        waste_generation_variability=0.0,
        treatment_conversion=(1.0, 0.0),
        transportation_time=(1.0, 0.0),
        generator_failure=None,
        collector_failure=None,
        treatment_failure=None,
    )
    fields.update(overrides)
    return ScenarioConfig(**fields)


def make_collector(env, waste_monitor, **overrides):
    """A real CollectorCompany in Podravska with one-tick-sized vehicles and no failures."""
    state = overrides.pop("state", None) or SimulationState()
    fields = dict(
        env=env,
        name="collector-1",
        waste_types=[WasteType.CONSTRUCTION_WOOD_17_02_01],
        collection_capacity=100.0,
        collection_frequency=12,
        transport_cost=10.0,
        efficiency=1.0,
        availability=True,
        region_type=RegionType.PODRAVSKA,
        scenario=deterministic_scenario(),
        waste_monitor=waste_monitor,
        kanban_manager=KanbanManager(),
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.REORDER_50,
        transport_manager=PointToPointTransport(state=state, road_circuity_mean=1.0),
        state=state,
        failure_config=None,
        seed=0,
    )
    fields.update(overrides)
    return CollectorCompany(**fields)


def make_treatment(env, waste_monitor, **overrides):
    """A real TreatmentOperator in Podravska with every catalogue route for its stored waste."""
    initial_waste_storage = overrides.get("initial_waste_storage", {})
    fields = dict(
        env=env,
        name="proc-1",
        processing_time=24,
        waste_storage_capacity=24_000.0,
        energy_consumption=100.0,
        environmental_impact=1.8,
        operational_costs=50.0,
        region_type=RegionType.PODRAVSKA,
        scenario=deterministic_scenario(),
        transformations=build_transformations(sorted_by_value(initial_waste_storage), list(OutputType)),
        waste_monitor=waste_monitor,
        kanban_manager=KanbanManager(),
        stock_strategy=StockStrategy.REORDER_50,
        inventory_policy=InventoryPolicy.PUSH,
        state=SimulationState(),
        failure_config=None,
        seed=0,
        abc_priority_map=SHIPPED_ABC_PRIORITY_WEIGHTS,
    )
    fields.update(overrides)
    return TreatmentOperator(**fields)


def make_waste_generator(env, waste_monitor, generation_rates, **overrides):
    """A real WasteGenerator in Podravska with exact (unit-factor) generation and no failures.

    Its first generation tick runs at t=0, where the seasonal factor is 1.0.
    """
    fields = dict(
        env=env,
        name="generator-1",
        waste_streams=generation_rates,
        generation_frequency=OPERATING_TICK_DAYS,
        waste_storage_capacity=1_000.0,
        efficiency=1.0,
        region_type=RegionType.PODRAVSKA,
        scenario=deterministic_scenario(),
        waste_monitor=waste_monitor,
        stock_strategy=StockStrategy.REORDER_50,
        inventory_policy=InventoryPolicy.PUSH,
        kanban_manager=KanbanManager(),
        state=SimulationState(),
        failure_config=None,
        seed=0,
    )
    fields.update(overrides)
    return WasteGenerator(**fields)


def make_generator_site(volume_by_type, name="generator-1", region_type=RegionType.PODRAVSKA):
    """The generator fields a collector pickup reads: name, region and per-type streams."""
    return SimpleNamespace(
        name=name,
        region_type=region_type,
        waste_streams={
            waste_type: WasteStream(waste_type=waste_type, volume=volume)
            for waste_type, volume in volume_by_type.items()
        },
        current_storage=sum(volume_by_type.values()),
    )


def posted_treatment_orders(waste_monitor, stock_strategy, on_hand, order_share_by_waste_type,
                            order_up_to_level_m3, waste_storage_capacity=100_000.0):
    """The per-type reorder volumes a PULL operator signals to its local collector in its first tick.

    The operator has no transformation routes, so nothing consumes ``on_hand``
    before the order is computed.
    """
    env = simpy.Environment()
    state = SimulationState()
    collector = make_collector(env, waste_monitor, state=state, inventory_policy=InventoryPolicy.PULL)
    state.collectors = [collector]
    make_treatment(
        env, waste_monitor, state=state, inventory_policy=InventoryPolicy.PULL,
        stock_strategy=stock_strategy, initial_waste_storage=on_hand, transformations={},
        order_share_by_waste_type=order_share_by_waste_type, order_up_to_level_m3=order_up_to_level_m3,
        waste_storage_capacity=waste_storage_capacity,
    )
    env.run(until=OPERATING_TICK_DAYS / 2)
    return {
        signal["waste_type"]: signal["volume"]
        for signal in collector.kanban_manager.get_signals()
        if signal["source_type"] == "treatment"
    }


EMPTY_PULL_OPERATOR_ORDER_M3 = 100.0


class RecordingKanbanManager(KanbanManager):
    """A real bus that also keeps the timestamp of every signal posted, before age pruning."""

    def __init__(self):
        super().__init__()
        self.posted_timestamps = []

    def add_signal(self, waste_type, timestamp, **signal):
        self.posted_timestamps.append(timestamp)
        super().add_signal(waste_type, timestamp, **signal)


def signal_recording_collector(region, stock):
    """A collector stand-in that supplies nothing and records the signals it receives."""
    return SimpleNamespace(
        name=f"collector-{region.value}",
        region_type=region,
        is_operational=True,
        status=EntityStatus.OPERATIONAL,
        inventory_policy=InventoryPolicy.PULL,
        collection_center=SimpleNamespace(current_storage=dict(stock)),
        kanban_manager=RecordingKanbanManager(),
        transferable_volume=lambda waste_type: 0.0,
        provide_waste_for_treatment=lambda *args, **kwargs: {},
    )


def run_empty_pull_operator(waste_monitor, collectors, generators=(), days=0.5, status=EntityStatus.OPERATIONAL):
    """Run a PULL operator holding no 17 02 01, so every tick orders EMPTY_PULL_OPERATOR_ORDER_M3 of it."""
    env = simpy.Environment()
    state = SimulationState()
    state.collectors = list(collectors)
    state.generators = list(generators)
    operator = make_treatment(
        env, waste_monitor, state=state, inventory_policy=InventoryPolicy.PULL, transformations={},
        order_share_by_waste_type={WasteType.CONSTRUCTION_WOOD_17_02_01: 1.0},
        order_up_to_level_m3=EMPTY_PULL_OPERATOR_ORDER_M3,
    )
    operator.status = status
    env.run(until=days)
    return operator
