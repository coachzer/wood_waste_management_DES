from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Tuple, List
from config.constants import SIMULATION_DURATION
from models.enums import InventoryPolicy, StockStrategy
from models.data_classes import FailureConfig
from utils.helpers import (
    validate_config, validate_all_numeric_positive
)

@dataclass
class UncertaintySet:
    """Uncertainty set - only variability parameters"""
    name: str
    collection_efficiency: Tuple[float, float]
    treatment_conversion: Tuple[float, float]
    transportation_time: Tuple[float, float]
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    waste_generation_variability: float = 0.2      # ±20% variation on regional rates

@dataclass
class CostParams:
    """Cost parameters"""
    landfill_per_m3: float = 20.4       # Cost per m³ landfilled ($46/tonne) (lebanon paper)
    expansion_cost_per_m3: float = 100.0  # Cost to expand storage by 1m³

DEFAULT_COSTS = CostParams()

@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario - unified and simplified"""
    name: str
    waste_gen: Tuple[float, float]
    coll_eff: Tuple[float, float]
    treat_conv: Tuple[float, float]
    trans_time: Tuple[float, float]
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    inventory_policy: InventoryPolicy = InventoryPolicy.PUSH
    stock_strategy: StockStrategy = StockStrategy.REORDER_90

    def to_uncertainty_set(self) -> UncertaintySet:
        """Convert scenario config to uncertainty set"""

        return UncertaintySet(
            # Required fields
            name = self.name,
            collection_efficiency=self.coll_eff,
            treatment_conversion=self.treat_conv,
            transportation_time=self.trans_time,
            generator_failure=self.generator_failure,
            collector_failure=self.collector_failure,
            treatment_failure=self.treatment_failure,
            waste_generation_variability=self.waste_gen[1]
        )

TIME_PERIODS = {
    "quarter_1": (0, 90),     # Q1: Jan-Mar (91 days)
    "quarter_2": (91, 181),   # Q2: Apr-Jun (91 days) 
    "quarter_3": (182, 272),  # Q3: Jul-Sep (91 days)
    "quarter_4": (273, 364),  # Q4: Oct-Dec (92 days)
}

LOW_FAILURE = FailureConfig(
    probability=0.0024,  # ~0.24% chance per day 
    min_duration=1.0,    # 1 day minimum
    max_duration=3.0,    # 3 days maximum
)

MEDIUM_FAILURE = FailureConfig(
    probability=0.06,    # ~6% chance per day 
    min_duration=0.5,    # 0.5 days (12 hours)
    max_duration=2.0,    # 2 days maximum
)

HIGH_FAILURE = FailureConfig(
    probability=0.12,    # ~12% chance per day 
    min_duration=0.25,   # 0.25 days (6 hours)
    max_duration=1.5,    # 1.5 days maximum
)

DISASTER_FAILURE = FailureConfig(
    probability=0.24,   # ~24% chance per day
    min_duration=0.25, # 30 days minimum
    max_duration=1.5,  # 60 days maximum
)

SCENARIO_CONFIGS: Dict[str, ScenarioConfig] = {
    "Baseline": ScenarioConfig(
        name="Baseline",
        waste_gen=(1.0, 0.1),    # Standard generation, low variability
        coll_eff=(0.85, 0.05),   # Good, stable collection efficiency
        treat_conv=(0.9, 0.03),  # High, stable conversion efficiency
        trans_time=(2.0, 0.2),   # Fast, predictable transport
        generator_failure=LOW_FAILURE,
        collector_failure=MEDIUM_FAILURE,
        treatment_failure=HIGH_FAILURE,
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.REORDER_90
    )# ,
    # "Disrupted": ScenarioConfig(
    #     name="Disrupted",
    #     waste_gen=(0.7, 0.5),    # Much lower, highly variable generation
    #     coll_eff=(0.5, 0.3),     # Poor, highly variable collection
    #     treat_conv=(0.6, 0.2),   # Poor, highly variable conversion
    #     trans_time=(5.0, 2.0),   # Slow, unpredictable transport
    #     generator_failure=LOW_FAILURE,
    #     collector_failure=HIGH_FAILURE,
    #     treatment_failure=HIGH_FAILURE,
    #     inventory_policy=InventoryPolicy.PUSH,
    #     stock_strategy=StockStrategy.ON_DEMAND
    # ),
    # "Boom": ScenarioConfig(
    #     name="Boom",
    #     waste_gen=(2.0, 0.2),    # Double generation, moderate variability
    #     coll_eff=(0.98, 0.02),   # Excellent, stable collection
    #     treat_conv=(0.98, 0.01), # Excellent, stable conversion
    #     trans_time=(1.0, 0.1),   # Very fast, predictable transport
    #     generator_failure=LOW_FAILURE,
    #     collector_failure=MEDIUM_FAILURE,
    #     treatment_failure=MEDIUM_FAILURE,
    #     inventory_policy=InventoryPolicy.PULL,
    #     stock_strategy=StockStrategy.REORDER_90
    # )
}

def validate_tuple(mean_std_tuple: Tuple[float, float], name: str) -> None:
    """Validate a mean/std tuple"""
    config_dict = {
        f"{name}_mean": mean_std_tuple[0],
        f"{name}_std": mean_std_tuple[1]
    }

    validate_all_numeric_positive(config_dict, allow_zero=True, exceptions=[f"{name}_std"])

    if mean_std_tuple[1] < 0:
        raise ValueError(f"{name} standard deviation must be non-negative")

def validate_scenario_config(config: ScenarioConfig) -> None:
    """Validate a scenario configuration"""
    validate_tuple(config.waste_gen, "Waste generation")
    validate_tuple(config.coll_eff, "Collection efficiency")
    validate_tuple(config.treat_conv, "Treatment conversion")
    validate_tuple(config.trans_time, "Transportation time")

uncertainty_sets = {}

def _create_uncertainty_set(config: ScenarioConfig) -> UncertaintySet:
    """Create uncertainty set from a scenario configuration"""
    return UncertaintySet(
        name=config.name,
        collection_efficiency=config.coll_eff,
        treatment_conversion=config.treat_conv,
        transportation_time=config.trans_time,
        generator_failure=config.generator_failure,
        collector_failure=config.collector_failure,
        treatment_failure=config.treatment_failure,
        waste_generation_variability=config.waste_gen[1] 
    )

def validate_time_periods() -> None:
    """Validate time period configuration"""
    validate_config(TIME_PERIODS, lambda periods: _validate_time_periods_internal(periods), "time periods")

def _validate_time_periods_internal(periods: Dict[str, Tuple[int, int]]) -> None:
    """Internal validation function for time periods"""
    total_units = sum(end - start + 1 for start, end in periods.values())
    if total_units != SIMULATION_DURATION:
        raise ValueError("Time periods don't match simulation duration")
    
    sorted_periods = sorted((start, end) for start, end in periods.values())
    for i in range(len(sorted_periods) - 1):
        if sorted_periods[i][1] + 1 != sorted_periods[i + 1][0]:
            raise ValueError("Time periods must be consecutive without gaps or overlaps")

validate_time_periods()
for scenario_name, config in SCENARIO_CONFIGS.items():
    validate_scenario_config(config)
    uncertainty_sets[scenario_name] = _create_uncertainty_set(config)

default_uncertainty_set = uncertainty_sets["Baseline"]

def get_uncertainty_set(scenario_name: str = "Baseline") -> UncertaintySet:
    """Get uncertainty set for a specific scenario"""
    try:
        return uncertainty_sets[scenario_name]
    except KeyError:
        raise KeyError(f"Uncertainty set '{scenario_name}' not found")

def get_scenario_config(scenario_name: str) -> ScenarioConfig:
    """Get scenario configuration by name"""
    if scenario_name not in SCENARIO_CONFIGS:
        raise KeyError(f"Scenario '{scenario_name}' not found")
    return SCENARIO_CONFIGS[scenario_name]

def get_scenario_with_strategies(
    base_scenario_name: str,
    inventory_policy: InventoryPolicy,
    stock_strategy: StockStrategy
) -> ScenarioConfig:
    """Create a scenario config by combining a base scenario with specific strategies"""
    base_scenario = SCENARIO_CONFIGS.get(base_scenario_name, SCENARIO_CONFIGS["Baseline"])
    
    modified_scenario = deepcopy(base_scenario)
    modified_scenario.name = f"{base_scenario_name}_{inventory_policy.value}_{stock_strategy.value}"
    modified_scenario.inventory_policy = inventory_policy
    modified_scenario.stock_strategy = stock_strategy
    
    return modified_scenario

def list_available_scenarios() -> List[str]:
    """List all available scenario names"""
    return list(SCENARIO_CONFIGS.keys())

def get_cost_params() -> CostParams:
    """Get default cost parameters"""
    return DEFAULT_COSTS