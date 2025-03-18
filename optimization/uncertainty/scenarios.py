from typing import Dict, List, Optional
import numpy as np
from models.enums import WasteType
from optimization.uncertainty.base import UncertaintySet

class ScenarioGenerationError(Exception):
    """Error during scenario generation"""
    pass

class ScenarioGenerator:
    """
    Generates scenarios for stochastic optimization
    
    This class handles the generation of scenarios based on uncertainty parameters,
    including the ability to adjust parameters over time and manage multiple
    scenario sets.
    
    Args:
        uncertainty_set: Set of uncertainty parameters
        num_scenarios: Number of scenarios to generate
        seed: Random seed for reproducibility
    """
    def __init__(
        self,
        uncertainty_set: UncertaintySet,
        num_scenarios: int = 100,
        seed: Optional[int] = None
    ):
        self.uncertainty_set = uncertainty_set
        self.base_uncertainty_set = uncertainty_set  # Store original values
        self.num_scenarios = num_scenarios
        self.rng = np.random.default_rng(seed if seed is not None else 42)
        
        # Track generation history
        self._generation_history: List[Dict] = []
        self._parameter_adjustments: List[Dict] = []

    def adjust_parameters(
        self,
        waste_generation_multiplier: float = 1.0,
        efficiency_multiplier: float = 1.0,
    ) -> None:
        """
        Adjust uncertainty parameters based on multipliers
        
        Args:
            waste_generation_multiplier: Factor to adjust waste generation rates
            efficiency_multiplier: Factor to adjust efficiency parameters
            
        Raises:
            ValueError: If multipliers are invalid
        """
        if waste_generation_multiplier <= 0:
            raise ValueError("Waste generation multiplier must be positive")
        if efficiency_multiplier <= 0:
            raise ValueError("Efficiency multiplier must be positive")

        # Record adjustment
        self._parameter_adjustments.append({
            "waste_generation": waste_generation_multiplier,
            "efficiency": efficiency_multiplier,
            "timestamp": len(self._parameter_adjustments)
        })

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

    def generate_scenarios(self, record_history: bool = True) -> List[Dict]:
        """
        Generate scenarios based on uncertainty distributions
        
        Args:
            record_history: Whether to record generated scenarios in history
            
        Returns:
            List of scenario dictionaries containing sampled parameters
            
        Raises:
            ScenarioGenerationError: If scenario generation fails
        """
        scenarios = []

        try:
            for _ in range(self.num_scenarios):
                scenario = self._generate_single_scenario()
                scenarios.append(scenario)

            if record_history:
                self._record_generation(scenarios)

            return scenarios
        except Exception as e:
            raise ScenarioGenerationError(f"Failed to generate scenarios: {str(e)}")

    def _generate_single_scenario(self) -> Dict:
        """Generate a single scenario"""
        return {
            "waste_generation": self._sample_waste_generation(),
            "collection_efficiency": self._sample_collection_efficiency(),
            "treatment_conversion": self._sample_treatment_conversion(),
            "transportation_time": self._sample_transportation_time(),
            "market_demand": self._sample_market_demand(),
            "equipment_status": self._sample_equipment_status(),
            "probability": 1.0 / self.num_scenarios,
        }

    def _sample_waste_generation(self) -> Dict[WasteType, float]:
        """Sample waste generation rates"""
        return {
            waste_type: max(0, self.rng.normal(mean, std))
            for waste_type, (mean, std) in self.uncertainty_set.waste_generation.items()
        }

    def _sample_collection_efficiency(self) -> float:
        """Sample collection efficiency"""
        mean, std = self.uncertainty_set.collection_efficiency
        return np.clip(self.rng.normal(mean, std), 0.5, 1.0)

    def _sample_treatment_conversion(self) -> Dict[WasteType, float]:
        """Sample treatment conversion rates"""
        return {
            waste_type: np.clip(self.rng.normal(mean, std), 0.6, 1.0)
            for waste_type, (mean, std) in self.uncertainty_set.treatment_conversion.items()
        }

    def _sample_transportation_time(self) -> float:
        """Sample transportation time"""
        mean, std = self.uncertainty_set.transportation_time
        return max(0.1, self.rng.normal(mean, std))

    def _sample_market_demand(self) -> Dict[WasteType, float]:
        """Sample market demand"""
        return {
            waste_type: max(0, self.rng.normal(mean, std))
            for waste_type, (mean, std) in self.uncertainty_set.market_demand.items()
        }

    def _sample_equipment_status(self) -> bool:
        """Sample equipment operational status"""
        return self.rng.random() > self.uncertainty_set.equipment_failure_rate

    def _record_generation(self, scenarios: List[Dict]) -> None:
        """Record scenario generation in history"""
        generation_stats = self._calculate_generation_stats(scenarios)
        self._generation_history.append(generation_stats)

    def _calculate_generation_stats(self, scenarios: List[Dict]) -> Dict:
        """Calculate statistics for a set of generated scenarios"""
        stats = {
            "num_scenarios": len(scenarios),
            "timestamp": len(self._generation_history),
            "waste_generation": {},
            "collection_efficiency": {
                "mean": np.mean([s["collection_efficiency"] for s in scenarios]),
                "std": np.std([s["collection_efficiency"] for s in scenarios])
            },
            "equipment_failures": sum(
                1 for s in scenarios if not s["equipment_status"]
            ) / len(scenarios)
        }

        # Calculate waste generation stats per type
        for waste_type in WasteType:
            values = [s["waste_generation"][waste_type] for s in scenarios]
            stats["waste_generation"][waste_type.value] = {
                "mean": np.mean(values),
                "std": np.std(values)
            }

        return stats

    def get_generation_history(self) -> List[Dict]:
        """Get history of scenario generation statistics"""
        return self._generation_history.copy()

    def get_parameter_adjustment_history(self) -> List[Dict]:
        """Get history of parameter adjustments"""
        return self._parameter_adjustments.copy()

    def reset_to_base_parameters(self) -> None:
        """Reset parameters to original values"""
        self.uncertainty_set = self.base_uncertainty_set
        self._parameter_adjustments = []
