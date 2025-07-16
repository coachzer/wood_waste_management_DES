"""
Base configuration for the simulation system.
Contains core simulation parameters, time settings, scenario configurations,
and uncertainty set generation.
"""
from dataclasses import dataclass
from typing import Dict, Tuple
from models.enums import WasteType, OutputType
from models.data_classes import FailureConfig
from utils.helpers import (
    load_json, validate_config, validate_all_numeric_positive
)

@dataclass
class UncertaintySet:
    """Simple uncertainty set replacement"""
    waste_generation: Dict
    collection_efficiency: Tuple[float, float]
    treatment_conversion: Dict
    transportation_time: Tuple[float, float]
    market_demand: Dict
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig

# Load demand data from JSON
_demand_data = load_json("data/demand.json")

@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario"""
    waste_gen: Tuple[float, float]
    coll_eff: Tuple[float, float]
    treat_conv: Tuple[float, float]
    trans_time: Tuple[float, float]
    market_dem: Tuple[float, float]
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    collaboration: bool

    def to_uncertainty_set(self) -> UncertaintySet:
        """Convert scenario config to uncertainty set"""
        # Set demand based on actual monthly demand values with some variation
        base_demand = {
            OutputType.WOODEN_PACKAGING: (MONTHLY_DEMAND[OutputType.WOODEN_PACKAGING], MONTHLY_DEMAND[OutputType.WOODEN_PACKAGING] * 0.2),
            OutputType.PAPER_PACKAGING: (MONTHLY_DEMAND[OutputType.PAPER_PACKAGING], MONTHLY_DEMAND[OutputType.PAPER_PACKAGING] * 0.2),
            OutputType.WOODEN_FURNITURE: (MONTHLY_DEMAND[OutputType.WOODEN_FURNITURE], MONTHLY_DEMAND[OutputType.WOODEN_FURNITURE] * 0.2)
        }

        # Set lower demand for input waste types
        input_demand = {
            waste_type: (demand * 0.1, demand * 0.02)  # 10% of output demand with less variation
            for waste_type, (demand, _) in base_demand.items()
        }

        # Combine demands
        market_demand = {**base_demand}
        for waste_type in WasteType:
            if waste_type not in market_demand:
                market_demand[waste_type] = input_demand.get(
                    waste_type,
                    (MONTHLY_DEMAND[OutputType.WOODEN_FURNITURE] * 0.05, MONTHLY_DEMAND[OutputType.WOODEN_FURNITURE] * 0.01)
                    if "FURNITURE" in waste_type.name
                    else (MONTHLY_DEMAND[OutputType.WOODEN_PACKAGING] * 0.05, MONTHLY_DEMAND[OutputType.WOODEN_PACKAGING] * 0.01)
                )

        # Create waste generation with values appropriate for input types
        waste_generation = {
            WasteType.SAWDUST: (3000, 600),          # High volume, fine particles
            WasteType.WOOD_CUTTINGS: (4000, 800),    # Large volume, structural elements
            WasteType.BARK_WASTE: (2000, 400),       # Medium volume
            WasteType.CONSTRUCTION_WOOD: (3500, 700), # Significant volume
            WasteType.MIXED_WOOD: (2500, 500),       # Medium volume
            # Recyclable packaging waste (based on market demand)
            WasteType.WASTE_WOODEN_PACKAGING: (1800, 360),  # ~15% of wooden packaging demand
            WasteType.WASTE_PAPER_PACKAGING: (1200, 240),   # ~15% of paper packaging demand
        }

        # Apply scenario multipliers
        waste_generation = {
            waste_type: (mean * self.waste_gen[0], std * self.waste_gen[1])
            for waste_type, (mean, std) in waste_generation.items()
        }

        treatment_conversion = {waste_type: self.treat_conv for waste_type in WasteType}

        return UncertaintySet(
            waste_generation=waste_generation,
            collection_efficiency=self.coll_eff,
            treatment_conversion=treatment_conversion,
            transportation_time=self.trans_time,
            market_demand=market_demand,
            generator_failure=self.generator_failure,
            collector_failure=self.collector_failure,
            treatment_failure=self.treatment_failure
        )

# Time configuration
SIMULATION_DURATION = 300  # 3 years * 100 time units per year
TIME_PERIOD = 100  # Length of one year in time units
TOTAL_YEARS = 3  # Total number of years to simulate

# Time periods documentation
TIME_PERIODS = {
    "year_1": (0, 99),    # First year time range
    "year_2": (100, 199), # Second year time range
    "year_3": (200, 299), # Third year time range
}

# Demand configuration from data/demand.json
MONTHLY_DEMAND = {
    OutputType.WOODEN_PACKAGING: _demand_data["national_demand"]["wooden_packaging"],
    OutputType.PAPER_PACKAGING: _demand_data["national_demand"]["paper_packaging"],
    OutputType.WOODEN_FURNITURE: _demand_data["national_demand"]["wooden_furniture"]
}

LOW_FAILURE = FailureConfig(
        probability=0.01,  # 1% chance per hour
        min_duration=12.0,
        max_duration=24.0,
        check_interval=24.0  # Check once per day
    )

MEDIUM_FAILURE = FailureConfig(
    probability=0.1,  # 10% chance per hour
    min_duration=6.0,
    max_duration=12.0,
    check_interval=12.0  # Check twice per day
)

HIGH_FAILURE = FailureConfig(
    probability=0.5,  # 50% chance per hour
    min_duration=3.0,
    max_duration=6.0,
    check_interval=6.0  # Check four times per day
)

# Default scenario configurations
SCENARIO_CONFIGS: Dict[str, ScenarioConfig] = {
    "Baseline": ScenarioConfig(
        waste_gen=(1.0, 0.2),    # Base generation rates
        coll_eff=(0.85, 0.1),    # Good collection efficiency
        treat_conv=(0.9, 0.05),  # High conversion efficiency
        trans_time=(2.0, 0.5),   # Standard transportation time
        market_dem=(1.0, 0.2),   # Base demand rates
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
        collaboration=False
    ),
    "High Uncertainty": ScenarioConfig(
        waste_gen=(1.0, 0.4),    # Same generation but more variance
        coll_eff=(0.85, 0.2),    # More variable collection
        treat_conv=(0.9, 0.1),   # More variable conversion
        trans_time=(2.0, 1.0),   # More variable transport
        market_dem=(1.0, 0.4),   # More variable demand
        generator_failure=HIGH_FAILURE,
        collector_failure=HIGH_FAILURE,
        treatment_failure=HIGH_FAILURE,
        collaboration=True
    ),
    "High Demand": ScenarioConfig(
        waste_gen=(1.5, 0.3),    # 50% more generation
        coll_eff=(0.85, 0.15),   # Standard collection
        treat_conv=(0.9, 0.05),  # Standard conversion
        trans_time=(2.0, 0.7),   # More variable transport due to volume
        market_dem=(1.5, 0.3),   # 50% more demand
        generator_failure=MEDIUM_FAILURE,
        collector_failure=MEDIUM_FAILURE,
        treatment_failure=MEDIUM_FAILURE,
        collaboration=True
    ),
    "Optimistic": ScenarioConfig(
        waste_gen=(1.2, 0.1),    # 20% more generation, very stable
        coll_eff=(0.95, 0.05),   # Higher and stable collection
        treat_conv=(0.95, 0.03), # Higher and stable conversion
        trans_time=(1.5, 0.3),   # Faster and stable transport
        market_dem=(1.2, 0.1),   # 20% more demand, very stable
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
        collaboration=True
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
    # Create waste generation with values appropriate for input types
    waste_generation = {
        # Primary materials
        WasteType.SAWDUST: (4320 * config.waste_gen[0], 864 * config.waste_gen[1]),
        WasteType.WOOD_CUTTINGS: (3780 * config.waste_gen[0], 756 * config.waste_gen[1]),
        WasteType.BARK_WASTE: (2850 * config.waste_gen[0], 570 * config.waste_gen[1]),
        WasteType.CONSTRUCTION_WOOD: (2130 * config.waste_gen[0], 426 * config.waste_gen[1]),
        WasteType.MIXED_WOOD: (2430 * config.waste_gen[0], 486 * config.waste_gen[1]),
        # Recyclable materials
        WasteType.WASTE_WOODEN_PACKAGING: (1800 * config.waste_gen[0], 360 * config.waste_gen[1]),
        WasteType.WASTE_PAPER_PACKAGING: (1200 * config.waste_gen[0], 240 * config.waste_gen[1]),
    }

    # Create treatment conversion rates
    treatment_conversion = {waste_type: config.treat_conv for waste_type in WasteType}

    # Create market demand from demand.json
    market_demand = {
        OutputType.WOODEN_PACKAGING: (_demand_data["national_demand"]["wooden_packaging"] * config.market_dem[0],
                                   _demand_data["national_demand"]["wooden_packaging"] * config.market_dem[1]),
        OutputType.PAPER_PACKAGING: (_demand_data["national_demand"]["paper_packaging"] * config.market_dem[0],
                                  _demand_data["national_demand"]["paper_packaging"] * config.market_dem[1]),
        OutputType.WOODEN_FURNITURE: (_demand_data["national_demand"]["wooden_furniture"] * config.market_dem[0],
                                   _demand_data["national_demand"]["wooden_furniture"] * config.market_dem[1]),
    }
    # Add input waste types with lower demand
    for waste_type in WasteType:
        if waste_type not in market_demand:
            market_demand[waste_type] = (600 * config.market_dem[0], 240 * config.market_dem[1])

    # Create uncertainty set
    return UncertaintySet(
        waste_generation=waste_generation,
        collection_efficiency=config.coll_eff,
        treatment_conversion=treatment_conversion,
        transportation_time=config.trans_time,
        market_demand=market_demand,
        generator_failure=config.generator_failure,
        collector_failure=config.collector_failure,
        treatment_failure=config.treatment_failure
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
