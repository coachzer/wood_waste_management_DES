from optimization.stochastic import UncertaintySet
from models.enums import WasteType
from typing import Dict, Tuple

class UncertaintySetFactory:
    """Factory methods for creating consistent uncertainty sets"""
    
    @staticmethod
    def create_waste_generation(base_mean: float, base_std: float) -> Dict[WasteType, Tuple[float, float]]:
        """Create waste generation dictionary with consistent values across waste types"""
        return {waste_type: (base_mean, base_std) for waste_type in WasteType}
        
    @staticmethod 
    def create_treatment_conversion(base_mean: float, base_std: float) -> Dict[WasteType, Tuple[float, float]]:
        """Create treatment conversion dictionary with consistent values across waste types"""
        return {waste_type: (base_mean, base_std) for waste_type in WasteType}

    @staticmethod
    def create_market_demand(base_mean: float, base_std: float) -> Dict[WasteType, Tuple[float, float]]:
        """Create market demand dictionary with consistent values across waste types"""
        return {waste_type: (base_mean, base_std) for waste_type in WasteType}

class ConfigValidator:
    """Validates configuration parameters"""
    
    @staticmethod
    def validate_uncertainty_set(uncertainty_set: UncertaintySet) -> None:
        """Validate uncertainty set parameters"""
        if not 0 <= uncertainty_set.equipment_failure_rate <= 1:
            raise ValueError("Equipment failure rate must be between 0 and 1")
            
        # Validate means and standard deviations
        for (mean, std) in uncertainty_set.waste_generation.values():
            if mean <= 0 or std < 0:
                raise ValueError("Mean must be positive and std must be non-negative")
        
        if uncertainty_set.collection_efficiency[0] <= 0 or uncertainty_set.collection_efficiency[1] < 0:
            raise ValueError("Collection efficiency mean must be positive and std non-negative")
            
        for (mean, std) in uncertainty_set.treatment_conversion.values():
            if mean <= 0 or std < 0:
                raise ValueError("Treatment conversion mean must be positive and std non-negative")
            
        if uncertainty_set.transportation_time[0] <= 0 or uncertainty_set.transportation_time[1] < 0:
            raise ValueError("Transportation time mean must be positive and std non-negative")
            
        for (mean, std) in uncertainty_set.market_demand.values():
            if mean <= 0 or std < 0:
                raise ValueError("Market demand mean must be positive and std non-negative")

    @staticmethod
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

# Time configuration
SIMULATION_DURATION = 300  # 3 years * 100 time units per year
TIME_PERIOD = 100  # Length of one year in time units
TOTAL_YEARS = 3  # Total number of years to simulate

# Time periods documentation
TIME_PERIODS = {
    "year_1": (0, 99),  # First year time range
    "year_2": (100, 199),  # Second year time range
    "year_3": (200, 299),  # Third year time range
}

# Scenario configuration parameters
SCENARIO_CONFIGS = {
    "Baseline": {
        "waste_gen": (1.0, 0.2),
        "coll_eff": (0.85, 0.1),
        "treat_conv": (0.9, 0.05),
        "trans_time": (2.0, 0.5),
        "market_dem": (1.0, 0.2),
        "equip_fail": 0.05,
        "collaboration": False
    },
    "High Uncertainty": {
        "waste_gen": (1.0, 0.4),
        "coll_eff": (0.85, 0.2),
        "treat_conv": (0.9, 0.1),
        "trans_time": (2.0, 1.0),
        "market_dem": (1.0, 0.4),
        "equip_fail": 0.1,
        "collaboration": True
    },
    "High Demand": {
        "waste_gen": (1.5, 0.3),
        "coll_eff": (0.85, 0.15),
        "treat_conv": (0.9, 0.05),
        "trans_time": (2.0, 0.7),
        "market_dem": (1.5, 0.3),
        "equip_fail": 0.05,
        "collaboration": True
    },
    "Optimistic": {
        "waste_gen": (1.2, 0.1),
        "coll_eff": (0.95, 0.05),
        "treat_conv": (0.95, 0.03),
        "trans_time": (1.5, 0.3),
        "market_dem": (1.2, 0.1),
        "equip_fail": 0.02,
        "collaboration": True
    }
}

# Create uncertainty sets using factory methods
uncertainty_sets = {}
for name, config in SCENARIO_CONFIGS.items():
    uncertainty_set = UncertaintySet(
        waste_generation=UncertaintySetFactory.create_waste_generation(*config["waste_gen"]),
        collection_efficiency=config["coll_eff"],
        treatment_conversion=UncertaintySetFactory.create_treatment_conversion(*config["treat_conv"]),
        transportation_time=config["trans_time"],
        market_demand=UncertaintySetFactory.create_market_demand(*config["market_dem"]),
        equipment_failure_rate=config["equip_fail"]
    )
    # Validate the uncertainty set
    ConfigValidator.validate_uncertainty_set(uncertainty_set)
    uncertainty_sets[name] = uncertainty_set

# Validate time periods configuration
ConfigValidator.validate_time_periods()

# Create scenarios with validated uncertainty sets
scenarios = {
    name: {
        "uncertainty_set": uncertainty_sets[name],
        "collaboration": config["collaboration"]
    }
    for name, config in SCENARIO_CONFIGS.items()
}
