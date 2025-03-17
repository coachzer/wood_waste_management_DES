import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
from models.enums import WasteType
from models.data_classes import FailureConfig

@dataclass
class UncertaintySet:
    """Defines uncertainty sets for stochastic parameters"""
    waste_generation: Dict[WasteType, Tuple[float, float]]  # (mean, std) for each waste type
    collection_efficiency: Tuple[float, float]  # (mean, std)
    treatment_conversion: Dict[WasteType, Tuple[float, float]]  # (mean, std) for each waste type
    transportation_time: Tuple[float, float]  # (mean, std)
    market_demand: Dict[WasteType, Tuple[float, float]]  # (mean, std) for each waste type
    generator_failure: FailureConfig  # Generator failure configuration
    collector_failure: FailureConfig  # Collector failure configuration
    treatment_failure: FailureConfig  # Treatment failure configuration

    @property
    def equipment_failure_rate(self) -> float:
        """Legacy support for equipment failure rate"""
        return max(
            self.generator_failure.probability,
            self.collector_failure.probability,
            self.treatment_failure.probability
        )

class ScenarioGenerator:
    """Generates scenarios for stochastic optimization"""

    def __init__(self, uncertainty_set: UncertaintySet, num_scenarios: int = 100):
        self.uncertainty_set = uncertainty_set
        self.base_uncertainty_set = uncertainty_set  # Store original values
        self.num_scenarios = num_scenarios
        self.rng = np.random.default_rng(42)  # For reproducibility

    def adjust_parameters(
        self,
        waste_generation_multiplier: float = 1.0,
        efficiency_multiplier: float = 1.0,
    ):
        """Adjust uncertainty parameters based on multipliers for different simulation years"""
        # Adjust waste generation parameters
        self.uncertainty_set.waste_generation = {
            waste_type: (mean * waste_generation_multiplier, std)
            for waste_type, (mean, std) in self.base_uncertainty_set.waste_generation.items()
        }

        # Adjust collection and treatment efficiencies
        mean, std = self.base_uncertainty_set.collection_efficiency
        self.uncertainty_set.collection_efficiency = (mean * efficiency_multiplier, std)

        self.uncertainty_set.treatment_conversion = {
            waste_type: (mean * efficiency_multiplier, std)
            for waste_type, (mean, std) in self.base_uncertainty_set.treatment_conversion.items()
        }

        # Adjust market demand proportionally to waste generation
        self.uncertainty_set.market_demand = {
            waste_type: (mean * waste_generation_multiplier, std)
            for waste_type, (mean, std) in self.base_uncertainty_set.market_demand.items()
        }

    def generate_scenarios(self) -> List[Dict]:
        """Generate scenarios based on uncertainty distributions"""
        scenarios = []

        for _ in range(self.num_scenarios):
            scenario = {
                "waste_generation": self._sample_waste_generation(),
                "collection_efficiency": self._sample_collection_efficiency(),
                "treatment_conversion": self._sample_treatment_conversion(),
                "transportation_time": self._sample_transportation_time(),
                "market_demand": self._sample_market_demand(),
                "equipment_status": self._sample_equipment_status(),
                "probability": 1.0 / self.num_scenarios,  # Equal probability for now
            }
            scenarios.append(scenario)

        return scenarios

    def _sample_waste_generation(self) -> Dict[WasteType, float]:
        """Sample waste generation rates for each waste type"""
        return {
            waste_type: self.rng.normal(mean, std)
            for waste_type, (mean, std) in self.uncertainty_set.waste_generation.items()
        }

    def _sample_collection_efficiency(self) -> float:
        """Sample collection efficiency"""
        mean, std = self.uncertainty_set.collection_efficiency
        return np.clip(self.rng.normal(mean, std), 0.5, 1.0)

    def _sample_treatment_conversion(self) -> Dict[WasteType, float]:
        """Sample treatment conversion rates for each waste type"""
        return {
            waste_type: np.clip(self.rng.normal(mean, std), 0.6, 1.0)
            for waste_type, (mean, std) in self.uncertainty_set.treatment_conversion.items()
        }

    def _sample_transportation_time(self) -> float:
        """Sample transportation time"""
        mean, std = self.uncertainty_set.transportation_time
        return max(0.1, self.rng.normal(mean, std))

    def _sample_market_demand(self) -> Dict[WasteType, float]:
        """Sample market demand for each waste type"""
        return {
            waste_type: max(0, self.rng.normal(mean, std))
            for waste_type, (mean, std) in self.uncertainty_set.market_demand.items()
        }

    def _sample_equipment_status(self) -> bool:
        """Sample equipment operational status"""
        return self.rng.random() > self.uncertainty_set.equipment_failure_rate

class TwoStageOptimizer:
    """Implements two-stage stochastic optimization"""

    def __init__(self, scenario_generator: ScenarioGenerator):
        self.scenario_generator = scenario_generator

    def optimize(self, risk_aversion: float = 0.5) -> Dict:
        """
        Perform two-stage stochastic optimization

        Args:
            risk_aversion: Risk aversion parameter (0-1), higher means more conservative

        Returns:
            Dictionary containing optimal first-stage decisions and expected second-stage costs
        """
        # Generate scenarios
        scenarios = self.scenario_generator.generate_scenarios()

        # First stage optimization (strategic decisions)
        first_stage_solution = self._optimize_first_stage(scenarios, risk_aversion)

        # Second stage optimization (operational decisions)
        second_stage_costs = []
        for scenario in scenarios:
            cost = self._optimize_second_stage(first_stage_solution, scenario)
            second_stage_costs.append(cost * scenario["probability"])

        return {
            "first_stage": first_stage_solution,
            "expected_second_stage_cost": sum(second_stage_costs),
            "scenarios_evaluated": len(scenarios),
        }

    def _optimize_first_stage(
        self, scenarios: List[Dict], risk_aversion: float
    ) -> Dict:
        """Optimize first-stage decisions (facility locations, capacities)"""
        # TODO: Implement facility location and capacity optimization
        # For now return placeholder solution
        return {
            "facility_locations": [],
            "storage_capacities": {},
            "processing_rates": {},
        }

    def _optimize_second_stage(self, first_stage: Dict, scenario: Dict) -> float:
        """Optimize second-stage decisions for given scenario"""
        # TODO: Implement operational optimization
        # For now return placeholder cost
        return 1000.0

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
