from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Tuple, List
from config.constants import (
    SIMULATION_DURATION,
    FINISHED_GOODS_BUFFER_WEEKS,
)
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

    Landfill cost is no longer a flat $/m³ here: handle_storage_event computes it
    per waste type from LANDFILL_COST_PER_TONNE_USD ($46/t deterrent gate cost,
    par with the EU-27 ~EUR 39-46/t range, CEWEP 2021 / EEA 2023) and each
    stream's own bulk density (WASTE_DENSITIES), per ADR 0013. The two escalation
    factors make each repeated overflow on an entity progressively more expensive
    (penalty grows with the count of prior expansions / landfills).
    """
    expansion_cost_per_m3: float = 100.0  # Cost to expand storage by 1m³
    expansion_cost_escalation_per_prior: float = 0.5  # per prior expansion on the entity
    landfill_cost_escalation_per_prior: float = 0.3  # per prior landfill on the entity

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
    )
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

for config in SCENARIO_CONFIGS.values():
    validate_scenario_config(config)

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
