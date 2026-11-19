"""Shared builders for core tests."""
import json

from config.base_config import ScenarioConfig
from core.abc_analysis import abc_priority_weights
from core.collector import CollectorCompany
from core.kanban_manager import KanbanManager
from core.transport_manager import PointToPointTransport
from core.treatment import TreatmentOperator
from models.enums import InventoryPolicy, OutputType, RegionType, StockStrategy, WasteType, sorted_by_value
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
