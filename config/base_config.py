from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple, List
from config.constants import SIMULATION_DURATION, DENSITY, FINISHED_GOODS_BUFFER_WEEKS
from models.enums import InventoryPolicy, StockStrategy
from models.data_classes import FailureConfig

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
    waste_generation_mean: float = 1.0               # Scenario multiplier on base rates
    waste_generation_variability: float = 0.2      # ±20% variation on regional rates
    finished_goods_buffer_weeks: int = FINISHED_GOODS_BUFFER_WEEKS  # weeks of demand sized into finished-goods capacity

@dataclass
class CostParams:
    """Cost parameters.

    landfill_per_m3 = $46/t (Lebanon) x 0.6 t/m³ = $27.6/m³, derived from DENSITY
    so it stays consistent if DENSITY changes. Anchors handle_storage_event's
    landfill-vs-expand decision.
    """
    landfill_per_m3: float = (
        46.0 * DENSITY
    )  # $46/tonne (lebanon paper) x DENSITY = 27.6 $/m³
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
    finished_goods_buffer_weeks: int = FINISHED_GOODS_BUFFER_WEEKS  # swept by the bucket-C sensitivity scenarios

    def to_uncertainty_set(self) -> UncertaintySet:
        """Convert scenario config to uncertainty set"""

        return UncertaintySet(
            name=self.name,
            collection_efficiency=self.coll_eff,
            treatment_conversion=self.treat_conv,
            transportation_time=self.trans_time,
            generator_failure=self.generator_failure,
            collector_failure=self.collector_failure,
            treatment_failure=self.treatment_failure,
            waste_generation_mean=self.waste_gen[0],
            waste_generation_variability=self.waste_gen[1],
            finished_goods_buffer_weeks=self.finished_goods_buffer_weeks
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
    min_duration=30.0,  # 30 days minimum
    max_duration=60.0,  # 60 days maximum
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

# Finished-goods buffer sensitivity sweep (bucket-C C1): each scenario is Baseline
# with only the finished-goods buffer resized, built from Baseline so shared
# parameters cannot drift. Buffer4 is the default and must reproduce Baseline.
BUFFER_SWEEP_WEEKS: Tuple[int, ...] = (2, 4, 6, 8)
for _buffer_weeks in BUFFER_SWEEP_WEEKS:
    _scenario = deepcopy(SCENARIO_CONFIGS["Baseline"])
    _scenario.name = f"Buffer{_buffer_weeks}"
    _scenario.finished_goods_buffer_weeks = _buffer_weeks
    SCENARIO_CONFIGS[_scenario.name] = _scenario

def validate_config(config: Any, validator: Callable[[Any], None], name: str) -> None:
    """Generic configuration validation helper

    Args:
        config: Configuration object to validate
        validator: Validation function to apply
        name: Name of the configuration (for error messages)
    """
    try:
        validator(config)
    except Exception as e:
        raise ValueError(f"Invalid {name} configuration: {str(e)}")

def validate_all_numeric_positive(
    config_dict: Dict[str, float],
    allow_zero: bool = False
) -> None:
    """Validate that all numeric values in a dictionary are positive

    Args:
        config_dict: Dictionary of configuration values
        allow_zero: Whether to allow zero values
    """
    for key, value in config_dict.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if allow_zero:
            if value < 0:
                raise ValueError(f"{key} must be non-negative")
        else:
            if value <= 0:
                raise ValueError(f"{key} must be positive")

def validate_tuple(mean_std_tuple: Tuple[float, float], name: str) -> None:
    """Validate a mean/std tuple

    Both mean and std are validated as non-negative via allow_zero=True. The std
    field previously carried a manual re-check after being excluded through an
    `exceptions` argument; that exclusion-then-recheck applied the identical
    `value < 0` rule, so it was redundant and has been removed.
    """
    config_dict = {
        f"{name}_mean": mean_std_tuple[0],
        f"{name}_std": mean_std_tuple[1]
    }

    validate_all_numeric_positive(config_dict, allow_zero=True)

def validate_scenario_config(config: ScenarioConfig) -> None:
    """Validate a scenario configuration"""
    validate_tuple(config.waste_gen, "Waste generation")
    validate_tuple(config.coll_eff, "Collection efficiency")
    validate_tuple(config.treat_conv, "Treatment conversion")
    validate_tuple(config.trans_time, "Transportation time")
    if config.finished_goods_buffer_weeks <= 0:
        raise ValueError("finished_goods_buffer_weeks must be positive")

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
        waste_generation_mean=config.waste_gen[0],
        waste_generation_variability=config.waste_gen[1],
        finished_goods_buffer_weeks=config.finished_goods_buffer_weeks
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
