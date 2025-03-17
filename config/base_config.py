"""
Base configuration for the simulation system.
Contains core simulation parameters, time settings, and scenario configurations.
"""
from dataclasses import dataclass
from typing import Dict, Tuple
from models.enums import WasteType
from models.data_classes import FailureConfig
from optimization.stochastic import UncertaintySet

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
            WasteType.WOODEN_PACKAGING: (MONTHLY_DEMAND[WasteType.WOODEN_PACKAGING], MONTHLY_DEMAND[WasteType.WOODEN_PACKAGING] * 0.2),
            WasteType.PAPER_PACKAGING: (MONTHLY_DEMAND[WasteType.PAPER_PACKAGING], MONTHLY_DEMAND[WasteType.PAPER_PACKAGING] * 0.2),
            WasteType.WOODEN_FURNITURE: (MONTHLY_DEMAND[WasteType.WOODEN_FURNITURE], MONTHLY_DEMAND[WasteType.WOODEN_FURNITURE] * 0.2)
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
                    (MONTHLY_DEMAND[WasteType.WOODEN_FURNITURE] * 0.05, MONTHLY_DEMAND[WasteType.WOODEN_FURNITURE] * 0.01)
                    if "FURNITURE" in waste_type.name
                    else (MONTHLY_DEMAND[WasteType.WOODEN_PACKAGING] * 0.05, MONTHLY_DEMAND[WasteType.WOODEN_PACKAGING] * 0.01)
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
            # Output types generate no waste
            WasteType.WOODEN_PACKAGING: (0, 0),
            WasteType.PAPER_PACKAGING: (0, 0),
            WasteType.WOODEN_FURNITURE: (0, 0)
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

# Demand configuration (from data/demand.json)
MONTHLY_DEMAND = {
    WasteType.WOODEN_PACKAGING: 600,
    WasteType.PAPER_PACKAGING: 500,
    WasteType.WOODEN_FURNITURE: 200
}

LOW_FAILURE = FailureConfig(
        probability=0.001,  # 0.1% chance per hour = ~2.4% per day
        min_duration=12.0,
        max_duration=24.0,
        check_interval=24.0  # Check once per day
    )

MEDIUM_FAILURE = FailureConfig(
    probability=0.01,  # 1% chance per hour = ~24% per day
    min_duration=6.0,
    max_duration=12.0,
    check_interval=12.0  # Check twice per day
)

HIGH_FAILURE = FailureConfig(
    probability=0.05,  # 5% chance per hour = ~100% per day
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

def validate_scenario_config(config: ScenarioConfig) -> None:
    """Validate a scenario configuration"""

    def validate_tuple(tup: Tuple[float, float], name: str) -> None:
        mean, std = tup
        if mean <= 0 or std < 0:
            raise ValueError(f"{name} mean must be positive and std non-negative")

    validate_tuple(config.waste_gen, "Waste generation")
    validate_tuple(config.coll_eff, "Collection efficiency")
    validate_tuple(config.treat_conv, "Treatment conversion")
    validate_tuple(config.trans_time, "Transportation time")
    validate_tuple(config.market_dem, "Market demand")

def validate_time_periods() -> None:
    """Validate time period configuration"""
    total_units = sum(end - start + 1 for start, end in TIME_PERIODS.values())
    if total_units != SIMULATION_DURATION:
        raise ValueError("Time periods don't match simulation duration")
    
    # Check for gaps and overlaps
    sorted_periods = sorted((start, end) for start, end in TIME_PERIODS.values())
    for i in range(len(sorted_periods) - 1):
        if sorted_periods[i][1] + 1 != sorted_periods[i + 1][0]:
            raise ValueError("Time periods must be consecutive without gaps or overlaps")

# Validate all configurations on import
validate_time_periods()
for scenario_name, config in SCENARIO_CONFIGS.items():
    validate_scenario_config(config)
