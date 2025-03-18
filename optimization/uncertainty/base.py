from dataclasses import dataclass
from typing import Dict, Tuple
from models.enums import WasteType
from models.data_classes import FailureConfig

@dataclass
class UncertaintySet:
    """
    Defines uncertainty sets for stochastic parameters
    
    Args:
        waste_generation: Mean and std dev for each waste type generation rate
        collection_efficiency: Mean and std dev for collection efficiency
        treatment_conversion: Mean and std dev for treatment conversion rates
        transportation_time: Mean and std dev for transportation times
        market_demand: Mean and std dev for market demand by waste type
        generator_failure: Configuration for generator failures
        collector_failure: Configuration for collector failures
        treatment_failure: Configuration for treatment failures
    """
    waste_generation: Dict[WasteType, Tuple[float, float]]
    collection_efficiency: Tuple[float, float]
    treatment_conversion: Dict[WasteType, Tuple[float, float]]
    transportation_time: Tuple[float, float]
    market_demand: Dict[WasteType, Tuple[float, float]]
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig

    def __post_init__(self):
        """Validate uncertainty set parameters"""
        self._validate_distribution_params()
        self._validate_failure_configs()

    def _validate_distribution_params(self):
        """Validate statistical distribution parameters"""
        # Validate waste generation parameters
        for waste_type, (mean, std) in self.waste_generation.items():
            if mean <= 0:
                raise ValueError(f"Mean waste generation for {waste_type} must be positive")
            if std < 0:
                raise ValueError(f"Standard deviation for {waste_type} must be non-negative")

        # Validate collection efficiency
        mean, std = self.collection_efficiency
        if not 0 < mean <= 1:
            raise ValueError(f"Mean collection efficiency must be between 0 and 1, got {mean}")
        if std < 0:
            raise ValueError("Collection efficiency std dev must be non-negative")

        # Validate treatment conversion rates
        for waste_type, (mean, std) in self.treatment_conversion.items():
            if not 0 < mean <= 1:
                raise ValueError(f"Mean conversion rate for {waste_type} must be between 0 and 1")
            if std < 0:
                raise ValueError(f"Conversion rate std dev for {waste_type} must be non-negative")

        # Validate transportation time
        mean, std = self.transportation_time
        if mean <= 0:
            raise ValueError(f"Mean transportation time must be positive")
        if std < 0:
            raise ValueError("Transportation time std dev must be non-negative")

        # Validate market demand
        for waste_type, (mean, std) in self.market_demand.items():
            if mean < 0:
                raise ValueError(f"Mean market demand for {waste_type} must be non-negative")
            if std < 0:
                raise ValueError(f"Market demand std dev for {waste_type} must be non-negative")

    def _validate_failure_configs(self):
        """Validate failure configuration parameters"""
        for config_name, config in [
            ("Generator", self.generator_failure),
            ("Collector", self.collector_failure),
            ("Treatment", self.treatment_failure),
        ]:
            if not 0 <= config.probability <= 1:
                raise ValueError(f"{config_name} failure probability must be between 0 and 1")
            if config.min_duration <= 0:
                raise ValueError(f"{config_name} minimum failure duration must be positive")
            if config.max_duration < config.min_duration:
                raise ValueError(
                    f"{config_name} maximum failure duration must be >= minimum duration"
                )
            if config.check_interval <= 0:
                raise ValueError(f"{config_name} check interval must be positive")

    @property
    def equipment_failure_rate(self) -> float:
        """Maximum equipment failure rate across all components"""
        return max(
            self.generator_failure.probability,
            self.collector_failure.probability,
            self.treatment_failure.probability
        )

def create_default_uncertainty_set() -> UncertaintySet:
    """Create default uncertainty set with reasonable values"""
    
    LOW_FAILURE = FailureConfig(
        probability=0.001,  # 0.1% chance per hour = ~2.4% per day
        min_duration=12.0,
        max_duration=24.0,
        check_interval=24.0  # Check once per day
    )
    
    return UncertaintySet(
        waste_generation={
            WasteType.SAWDUST: (100, 20),
            WasteType.WOOD_CUTTINGS: (80, 15),
            WasteType.BARK_WASTE: (60, 10),
            WasteType.CONSTRUCTION_WOOD: (120, 25),
            WasteType.WASTE_PAPER_PACKAGING: (90, 18),
            WasteType.WASTE_WOODEN_PACKAGING: (70, 14),
            WasteType.MIXED_WOOD: (50, 10),
        },
        collection_efficiency=(0.85, 0.1),
        treatment_conversion={waste_type: (0.9, 0.05) for waste_type in WasteType},
        transportation_time=(2.0, 0.5),
        market_demand={waste_type: (200, 40) for waste_type in WasteType},
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
    )
