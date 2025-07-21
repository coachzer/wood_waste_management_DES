# Note: Actual waste generation rates come from regional JSON files
# This only provides the uncertainty/variability factors

from dataclasses import dataclass
from typing import Dict, Tuple, List
from models.enums import WasteType, OutputType, InventoryPolicy, StockStrategy, CoordinationStrategy
from models.data_classes import FailureConfig
from utils.helpers import (
    load_json, validate_config, validate_all_numeric_positive
)

@dataclass
class UncertaintySet:
    """Simplified uncertainty set - only variability parameters"""
    # Required fields first
    collection_efficiency: Tuple[float, float]
    treatment_conversion: Tuple[float, float]
    transportation_time: Tuple[float, float]
    market_demand: Dict
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    waste_generation_variability: float = 0.2      # ±20% variation on regional rates
    
# Load demand data from JSON
_demand_data = load_json("data/demand.json")

@dataclass
class CostParams:
    """Simplified cost parameters"""
    processing_rate: float = 50.0      # Cost per unit processed
    transport_rate: float = 2.0        # Cost per unit per km
    storage_rate: float = 1.0          # Cost per unit per time period
    energy_rate: float = 0.15          # Cost per kWh
    landfill_rate: float = 75.0        # Cost per unit landfilled

DEFAULT_COSTS = CostParams()

@dataclass
class FacilityParams:
    """Simplified facility parameters"""
    base_storage_capacity: float = 5000.0     # Base storage capacity
    base_processing_efficiency: float = 0.85   # Base processing efficiency
    base_processing_time: float = 1.2         # Base processing time
    energy_consumption: float = 1.0           # Base energy consumption

DEFAULT_FACILITY = FacilityParams()

# Key waste types for the system (simplified list)
PRIMARY_WASTE_TYPES = [
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
    WasteType.BARK_WASTE_03_01_01,
    WasteType.CONSTRUCTION_WOOD_17_02_01,
    WasteType.NON_HAZARDOUS_WOOD_20_01_38,
    WasteType.WOODEN_PACKAGING_15_01_03,
    WasteType.PAPER_PACKAGING_15_01_01
]

# Base transformation efficiencies (waste_type -> efficiency)
BASE_TRANSFORMATIONS = {
    WasteType.CONSTRUCTION_WOOD_17_02_01: 0.98,
    WasteType.WOODEN_PACKAGING_15_01_03: 0.88,
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 0.95,
    WasteType.BARK_WASTE_03_01_01: 0.85,
    WasteType.NON_HAZARDOUS_WOOD_20_01_38: 0.88,
    WasteType.PAPER_PACKAGING_15_01_01: 0.82,
}

@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario - unified and simplified"""
    name: str
    waste_gen: Tuple[float, float]
    coll_eff: Tuple[float, float]
    treat_conv: Tuple[float, float]
    trans_time: Tuple[float, float]
    market_dem: Tuple[float, float]
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    collaboration: bool
    # Scenario behavior parameters
    inventory_policy: InventoryPolicy = InventoryPolicy.PUSH
    stock_strategy: StockStrategy = StockStrategy.FULL_STOCK
    coordination_strategy: CoordinationStrategy = CoordinationStrategy.COMPETITIVE

    def to_uncertainty_set(self) -> UncertaintySet:
        """Convert scenario config to uncertainty set"""
        # Market demand based on actual monthly demand values
        market_demand = {
            OutputType.MDF_FIBREBOARD: (
                MONTHLY_DEMAND[OutputType.MDF_FIBREBOARD] * self.market_dem[0], 
                MONTHLY_DEMAND[OutputType.MDF_FIBREBOARD] * self.market_dem[1]),
            OutputType.PARTICLE_BOARD: (
                MONTHLY_DEMAND[OutputType.PARTICLE_BOARD] * self.market_dem[0],
                MONTHLY_DEMAND[OutputType.PARTICLE_BOARD] * self.market_dem[1]),
            OutputType.OSB_WAFERBOARD: (
                MONTHLY_DEMAND[OutputType.OSB_WAFERBOARD] * self.market_dem[0],
                MONTHLY_DEMAND[OutputType.OSB_WAFERBOARD] * self.market_dem[1])
        }

        # Add reasonable demand for waste types (lower than output products)
        for waste_type in WasteType:
            if waste_type not in market_demand:
                market_demand[waste_type] = (600 * self.market_dem[0], 240 * self.market_dem[1])

        return UncertaintySet(
            # Required fields
            collection_efficiency=self.coll_eff,
            treatment_conversion=self.treat_conv,
            transportation_time=self.trans_time,
            market_demand=market_demand,
            generator_failure=self.generator_failure,
            collector_failure=self.collector_failure,
            treatment_failure=self.treatment_failure,
            # Optional field
            waste_generation_variability=self.waste_gen[1]  # Use std as variability factor
        )

# Time configuration
SIMULATION_DURATION = 365  # days in simulation (one full year)
TIME_STEP = 1  # days per time step

TIME_PERIODS = {
    "quarter_1": (0, 90),     # Q1: Jan-Mar (91 days)
    "quarter_2": (91, 181),   # Q2: Apr-Jun (91 days) 
    "quarter_3": (182, 272),  # Q3: Jul-Sep (91 days)
    "quarter_4": (273, 364),  # Q4: Oct-Dec (92 days)
}

# Demand configuration from data/demand.json - to check the file and UPDATE
MONTHLY_DEMAND = {
    OutputType.MDF_FIBREBOARD: _demand_data["national_demand"]["mdf_fibreboard"],
    OutputType.PARTICLE_BOARD: _demand_data["national_demand"]["particle_board"],
    OutputType.OSB_WAFERBOARD: _demand_data["national_demand"]["osb_waferboard"]
}

LOW_FAILURE = FailureConfig(
    probability=0.001,  # 0.1% chance per hour = ~2.4% chance per day
    min_duration=12.0,
    max_duration=24.0,
    check_interval=24.0  # Check once per day
    )

MEDIUM_FAILURE = FailureConfig(
    probability=0.005,  # 0.5% chance per hour = ~12% chance per day
    min_duration=6.0,
    max_duration=12.0,
    check_interval=12.0  # Check twice per day
)

HIGH_FAILURE = FailureConfig(
    probability=0.01,  # 1% chance per hour = ~24% chance per day
    min_duration=3.0,
    max_duration=6.0,
    check_interval=6.0  # Check four times per day
)

# Default scenario configurations - simplified and unified
SCENARIO_CONFIGS: Dict[str, ScenarioConfig] = {
    "Baseline": ScenarioConfig(
        name="Baseline",
        waste_gen=(1.0, 0.2),    # Base generation rates
        coll_eff=(0.85, 0.1),    # Good collection efficiency
        treat_conv=(0.9, 0.05),  # High conversion efficiency
        trans_time=(2.0, 0.5),   # Standard transportation time
        market_dem=(1.0, 0.2),   # Base demand rates
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
        collaboration=False,
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.FULL_STOCK,
        coordination_strategy=CoordinationStrategy.COMPETITIVE
    ),
    "High Uncertainty": ScenarioConfig(
        name="High Uncertainty",
        waste_gen=(1.0, 0.4),    # Same generation but more variance
        coll_eff=(0.85, 0.2),    # More variable collection
        treat_conv=(0.9, 0.1),   # More variable conversion
        trans_time=(2.0, 1.0),   # More variable transport
        market_dem=(1.0, 0.4),   # More variable demand
        generator_failure=HIGH_FAILURE,
        collector_failure=HIGH_FAILURE,
        treatment_failure=HIGH_FAILURE,
        collaboration=True,
        inventory_policy=InventoryPolicy.PULL,
        stock_strategy=StockStrategy.ON_DEMAND,
        coordination_strategy=CoordinationStrategy.COLLABORATIVE
    ),
    "High Demand": ScenarioConfig(
        name="High Demand",
        waste_gen=(1.5, 0.3),    # 50% more generation
        coll_eff=(0.85, 0.15),   # Standard collection
        treat_conv=(0.9, 0.05),  # Standard conversion
        trans_time=(2.0, 0.7),   # More variable transport due to volume
        market_dem=(1.5, 0.3),   # 50% more demand
        generator_failure=MEDIUM_FAILURE,
        collector_failure=MEDIUM_FAILURE,
        treatment_failure=MEDIUM_FAILURE,
        collaboration=True,
        inventory_policy=InventoryPolicy.PULL,
        stock_strategy=StockStrategy.REORDER_90,
        coordination_strategy=CoordinationStrategy.COLLABORATIVE
    ),
    "Optimistic": ScenarioConfig(
        name="Optimistic",
        waste_gen=(1.2, 0.1),    # 20% more generation, very stable
        coll_eff=(0.95, 0.05),   # Higher and stable collection
        treat_conv=(0.95, 0.03), # Higher and stable conversion
        trans_time=(1.5, 0.3),   # Faster and stable transport
        market_dem=(1.2, 0.1),   # 20% more demand, very stable
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
        collaboration=True,
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.FULL_STOCK,
        coordination_strategy=CoordinationStrategy.COLLABORATIVE
    )
}

def validate_tuple(tup: Tuple[float, float], name: str) -> None:
    """Validate a mean/std tuple"""
    # Create a dictionary for the numeric validation
    config_dict = {
        f"{name}_mean": tup[0],
        f"{name}_std": tup[1]
    }
    # Validate mean is positive and std is non-negative
    validate_all_numeric_positive(config_dict, allow_zero=True, exceptions=[f"{name}_std"])
    # Additional validation for std
    if tup[1] < 0:
        raise ValueError(f"{name} standard deviation must be non-negative")

def validate_scenario_config(config: ScenarioConfig) -> None:
    """Validate a scenario configuration"""
    validate_tuple(config.waste_gen, "Waste generation")
    validate_tuple(config.coll_eff, "Collection efficiency")
    validate_tuple(config.treat_conv, "Treatment conversion")
    validate_tuple(config.trans_time, "Transportation time")
    validate_tuple(config.market_dem, "Market demand")

# Collection of generated uncertainty sets
uncertainty_sets = {}

def _create_uncertainty_set(config: ScenarioConfig) -> UncertaintySet:
    """Create uncertainty set from a scenario configuration"""
    # Market demand from demand.json
    market_demand = {
        OutputType.MDF_FIBREBOARD: (
            _demand_data["national_demand"]["mdf_fibreboard"] * config.market_dem[0],
            _demand_data["national_demand"]["mdf_fibreboard"] * config.market_dem[1]),
        OutputType.PARTICLE_BOARD: (
            _demand_data["national_demand"]["particle_board"] * config.market_dem[0],
            _demand_data["national_demand"]["particle_board"] * config.market_dem[1]),
        OutputType.OSB_WAFERBOARD: (
            _demand_data["national_demand"]["osb_waferboard"] * config.market_dem[0],
            _demand_data["national_demand"]["osb_waferboard"] * config.market_dem[1]),
    }
    
    # Add reasonable demand for waste types (lower than output products)
    for waste_type in WasteType:
        if waste_type not in market_demand:
            market_demand[waste_type] = (600 * config.market_dem[0], 240 * config.market_dem[1])

    # Create uncertainty set with variability factors
    return UncertaintySet(
        # Required fields
        collection_efficiency=config.coll_eff,
        treatment_conversion=config.treat_conv,
        transportation_time=config.trans_time,
        market_demand=market_demand,
        generator_failure=config.generator_failure,
        collector_failure=config.collector_failure,
        treatment_failure=config.treatment_failure,
        # Optional field
        waste_generation_variability=config.waste_gen[1]  # Use std as variability factor
    )

def validate_time_periods() -> None:
    """Validate time period configuration"""
    validate_config(TIME_PERIODS, lambda periods: _validate_time_periods_internal(periods), "time periods")

def _validate_time_periods_internal(periods: Dict[str, Tuple[int, int]]) -> None:
    """Internal validation function for time periods"""
    total_units = sum(end - start + 1 for start, end in periods.values())
    if total_units != SIMULATION_DURATION:
        raise ValueError("Time periods don't match simulation duration")
    
    # Check for gaps and overlaps
    sorted_periods = sorted((start, end) for start, end in periods.values())
    for i in range(len(sorted_periods) - 1):
        if sorted_periods[i][1] + 1 != sorted_periods[i + 1][0]:
            raise ValueError("Time periods must be consecutive without gaps or overlaps")

# Generate uncertainty sets and validate configurations on import
validate_time_periods()
for scenario_name, config in SCENARIO_CONFIGS.items():
    validate_scenario_config(config)
    uncertainty_sets[scenario_name] = _create_uncertainty_set(config)

# Set default uncertainty set
default_uncertainty_set = uncertainty_sets["Baseline"]

def get_uncertainty_set(scenario_name: str = "Baseline") -> UncertaintySet:
    """Get uncertainty set for a specific scenario"""
    return uncertainty_sets.get(scenario_name, default_uncertainty_set)

def get_scenario_config(scenario_name: str = "Baseline") -> ScenarioConfig:
    """Get scenario configuration by name"""
    return SCENARIO_CONFIGS.get(scenario_name, SCENARIO_CONFIGS["Baseline"])

def get_scenario_by_params(
    inventory_policy: InventoryPolicy = InventoryPolicy.PUSH,
    stock_strategy: StockStrategy = StockStrategy.FULL_STOCK,
    coordination_strategy: CoordinationStrategy = CoordinationStrategy.COMPETITIVE
) -> ScenarioConfig:
    """Get scenario configuration by behavioral parameters"""
    # Find first scenario that matches the parameters
    for scenario in SCENARIO_CONFIGS.values():
        if (scenario.inventory_policy == inventory_policy and 
            scenario.stock_strategy == stock_strategy and
            scenario.coordination_strategy == coordination_strategy):
            return scenario
    
    # If no exact match, return baseline
    return SCENARIO_CONFIGS["Baseline"]

def list_available_scenarios() -> List[str]:
    """List all available scenario names"""
    return list(SCENARIO_CONFIGS.keys())

# Convenience functions for costs and facility parameters
def get_cost_params() -> CostParams:
    """Get default cost parameters"""
    return DEFAULT_COSTS

def get_facility_params() -> FacilityParams:
    """Get default facility parameters"""
    return DEFAULT_FACILITY
