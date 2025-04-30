from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
from functools import lru_cache
import numpy as np
from optimization.stochastic import ScenarioGenerator
from core.cost_tracker import CostType
from models.state import SimulationState
from models.enums import WasteType

@dataclass
class ObjectiveResult:
    """
    Result of an objective evaluation
    
    Args:
        score: Raw score from the evaluation
        weight: Weight of this objective in the overall optimization
        should_minimize: Whether lower scores are better
        risk_measure: Value at Risk (VaR) or other risk metric
        scenarios_evaluated: Number of scenarios evaluated
    """
    score: float
    weight: float
    should_minimize: bool
    risk_measure: float = 0.0
    scenarios_evaluated: int = 1

    def __post_init__(self):
        """Validate result parameters after initialization"""
        if not isinstance(self.score, (int, float)):
            raise ValueError(f"Score must be numeric, got {type(self.score)}")
        if not 0 <= self.weight <= 1:
            raise ValueError(f"Weight must be between 0 and 1, got {self.weight}")

class ObjectiveError(Exception):
    """Base class for objective-related errors"""
    pass

class ScenarioError(ObjectiveError):
    """Error applying a scenario to the state"""
    pass

class OptimizationObjective(ABC):
    """
    Base class for optimization objectives
    
    Args:
        weight: Weight of this objective in the overall optimization (0-1)
        should_minimize: Whether lower scores are better
        risk_aversion: Risk aversion parameter for stochastic evaluation (0-1)
        cache_size: Size of LRU cache for evaluation results
    """
    def __init__(
        self,
        weight: float,
        should_minimize: bool,
        risk_aversion: float = 0.5,
        cache_size: int = 128
    ):
        if not 0 <= weight <= 1:
            raise ValueError(f"Weight must be between 0 and 1, got {weight}")
        if not 0 <= risk_aversion <= 1:
            raise ValueError(f"Risk aversion must be between 0 and 1, got {risk_aversion}")
            
        self.weight = weight
        self.should_minimize = should_minimize
        self.risk_aversion = risk_aversion
        self.scenario_generator = None
        
        # Configure caching
        self.evaluate = lru_cache(maxsize=cache_size)(self.evaluate)

    def set_scenario_generator(self, scenario_generator: ScenarioGenerator):
        """
        Set the scenario generator for stochastic evaluation
        
        Args:
            scenario_generator: ScenarioGenerator instance to use
        """
        self.scenario_generator = scenario_generator

    @abstractmethod
    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate the objective for a given state
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the evaluation results
        """
        pass

    def evaluate_stochastic(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate the objective across multiple scenarios
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing aggregated results across scenarios
        """
        if not self.scenario_generator:
            return self.evaluate(state)

        try:
            scenarios = self.scenario_generator.generate_scenarios()
            scenario_scores = []

            for scenario in scenarios:
                try:
                    scenario_state = self._apply_scenario(state, scenario)
                    result = self.evaluate(scenario_state)
                    scenario_scores.append(result.score)
                except Exception as e:
                    print(f"Warning: Failed to evaluate scenario: {str(e)}")
                    continue

            if not scenario_scores:
                raise ScenarioError("No valid scenarios could be evaluated")

            # Calculate risk-aware score
            mean_score = np.mean(scenario_scores)
            percentile = 95 if self.should_minimize else 5
            var_95 = np.percentile(scenario_scores, percentile)
            final_score = (1 - self.risk_aversion) * mean_score + self.risk_aversion * var_95

            return ObjectiveResult(
                score=final_score,
                weight=self.weight,
                should_minimize=self.should_minimize,
                risk_measure=var_95,
                scenarios_evaluated=len(scenarios),
            )
        except Exception as e:
            raise ScenarioError(f"Failed to evaluate scenarios: {str(e)}")

    def _apply_scenario(self, state: SimulationState, scenario: Dict[str, Any]) -> SimulationState:
        """
        Apply scenario parameters to create a new state
        
        Args:
            state: Base simulation state
            scenario: Dictionary of scenario parameters
            
        Returns:
            New SimulationState with scenario parameters applied
        
        Raises:
            ScenarioError: If scenario application fails
        """
        try:
            new_state = state.copy()
            
            # Apply waste generation scenario
            if "waste_generation" in scenario:
                self._apply_waste_generation_scenario(new_state, scenario["waste_generation"])

            # Apply collection efficiency scenario
            if "collection_efficiency" in scenario:
                self._apply_collection_scenario(new_state, scenario["collection_efficiency"])

            # Apply treatment conversion scenario
            if "treatment_conversion" in scenario:
                self._apply_treatment_scenario(new_state, scenario["treatment_conversion"])

            # Apply equipment status scenario
            if "equipment_status" in scenario:
                self._apply_equipment_scenario(new_state, scenario["equipment_status"])

            return new_state
        except Exception as e:
            raise ScenarioError(f"Failed to apply scenario: {str(e)}")

    def _apply_waste_generation_scenario(
        self, state: SimulationState, scenario_rates: Dict[WasteType, float]
    ):
        """Apply waste generation rates to generators"""
        for generator in state.generators:
            for waste_type, rate in scenario_rates.items():
                if waste_type in generator.waste_generation_rates:
                    generator.waste_generation_rates[waste_type] *= rate

    def _apply_collection_scenario(
        self, state: SimulationState, efficiency: float
    ):
        """Apply collection efficiency to collectors"""
        for collector in state.collectors:
            collector.efficiency *= efficiency

    def _apply_treatment_scenario(
        self, state: SimulationState, conversion_rates: Dict[WasteType, float]
    ):
        """Apply treatment conversion rates to operators"""
        for operator in state.treatment_operators:
            for waste_type, rate in conversion_rates.items():
                if waste_type in operator.transformations:
                    operator.transformations[waste_type].conversion_efficiency *= rate

    def _apply_equipment_scenario(
        self, state: SimulationState, operational: bool
    ):
        """Apply equipment operational status"""
        if not operational:
            # Reduce efficiency of all equipment
            for generator in state.generators:
                generator.efficiency *= 0.5
            for collector in state.collectors:
                collector.efficiency *= 0.5
            for operator in state.treatment_operators:
                operator.conversion_rate *= 0.5

    def normalize_score(self, score: float) -> float:
        """
        Normalize a score to a 0-1 range
        
        Args:
            score: Raw score to normalize
            
        Returns:
            Normalized score between 0 and 1
        """
        if self.should_minimize:
            # For minimization objectives, use inverse normalization
            # This ensures that lower raw scores result in higher normalized scores
            return 1 / (1 + max(0, score))
        else:
            # For maximization objectives, use sigmoid-like normalization
            # This ensures scores are bounded between 0 and 1
            return score / (1 + abs(score))

class StorageUtilizationObjective(OptimizationObjective):
    """Evaluates storage utilization and robustness across the system"""

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        utilizations = []
        margins = []

        # Check both generators and treatment operators
        for generator in state.generators:
            if generator.storage_capacity > 0:
                utilization = generator.current_storage / generator.storage_capacity
                margin = (
                    generator.storage_capacity - generator.current_storage
                ) / generator.storage_capacity
                utilizations.append(utilization)
                margins.append(margin)

        for operator in state.treatment_operators:
            if operator.storage_capacity > 0:
                utilization = operator.current_storage / operator.storage_capacity
                margin = (
                    operator.storage_capacity - operator.current_storage
                ) / operator.storage_capacity
                utilizations.append(utilization)
                margins.append(margin)

        if not utilizations:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        # Combine utilization and margin scores
        avg_utilization = np.mean(utilizations)
        avg_margin = np.mean(margins)

        # Calculate standard deviations for variability analysis
        util_std = np.std(utilizations) if len(utilizations) > 1 else 0
        margin_std = np.std(margins) if len(margins) > 1 else 0

        # Penalize high variability
        util_score = avg_utilization * (1 - 0.5 * util_std)
        margin_score = avg_margin * (1 - 0.5 * margin_std)

        # Balance between utilization and safety margin
        score = 0.7 * util_score + 0.3 * margin_score
        return ObjectiveResult(score, self.weight, self.should_minimize)

class CollectionEfficiencyObjective(OptimizationObjective):
    """Evaluates collection efficiency and reliability"""

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        if not state.collectors:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        scores = []
        total_capacity = 0
        total_collected = 0

        for collector in state.collectors:
            # Collection efficiency
            collection_amount = sum(collector.collected_waste.values())
            capacity = collector.collection_capacity
            
            # Skip collectors with zero capacity
            if capacity <= 0:
                continue
                
            collection_rate = collection_amount / capacity
            total_capacity += capacity
            total_collected += collection_amount

            # Reliability and operational efficiency
            reliability = collector.efficiency
            cost_factor = 1 / (1 + (collector.transport_cost / 100))

            # Combined score with weights
            score = 0.5 * collection_rate + 0.3 * reliability + 0.2 * cost_factor
            scores.append(score)

        if not scores:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        # Calculate system-wide collection rate
        system_rate = total_collected / total_capacity if total_capacity > 0 else 0

        # Combine individual scores and system-wide rate
        final_score = 0.7 * np.mean(scores) + 0.3 * system_rate
        return ObjectiveResult(final_score, self.weight, self.should_minimize)

class OverflowPenaltyObjective(OptimizationObjective):
    """Evaluates overflow penalties across the system"""

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        total_penalty = 0
        total_capacity = 0

        for generator in state.generators:
            total_penalty += generator.overflow_tracker.total_landfilled
            total_capacity += generator.storage_capacity

        for collector in state.collectors:
            total_penalty += collector.overflow_tracker.total_landfilled
            total_capacity += collector.collection_capacity

        for operator in state.treatment_operators:
            total_penalty += operator.overflow_tracker.total_landfilled
            total_capacity += operator.storage_capacity

        # Normalize penalty relative to total system capacity
        if total_capacity > 0:
            normalized_penalty = total_penalty / total_capacity
        else:
            normalized_penalty = total_penalty

        return ObjectiveResult(normalized_penalty, self.weight, self.should_minimize)

class TreatmentEfficiencyObjective(OptimizationObjective):
    """Evaluates treatment efficiency, reliability, and environmental impact"""

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        if not state.treatment_operators:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        scores = []
        weights = []
        total_capacity = 0

        for operator in state.treatment_operators:
            # Skip operators with no capacity
            if operator.storage_capacity <= 0:
                continue
                
            total_capacity += operator.storage_capacity
            
            # Processing efficiency
            processing_efficiency = operator.conversion_rate

            # Storage efficiency
            storage_efficiency = 1 - (
                operator.current_storage / operator.storage_capacity
            )

            # Energy efficiency (inverse of consumption)
            energy_efficiency = 1 / (1 + operator.energy_consumption)

            # Environmental impact (normalized)
            impact_map = {"Low": 0.9, "Moderate": 0.6, "High": 0.3}
            env_factor = impact_map.get(operator.environmental_impact, 0.5)

            # Combined score with weights
            score = (
                0.4 * processing_efficiency
                + 0.3 * storage_efficiency
                + 0.2 * energy_efficiency
                + 0.1 * env_factor
            )
            
            # Weight by capacity
            weight = operator.storage_capacity / total_capacity if total_capacity > 0 else 0
            scores.append(score)
            weights.append(weight)

        if not scores:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        # Calculate weighted average score
        final_score = np.average(scores, weights=weights)
        return ObjectiveResult(final_score, self.weight, self.should_minimize)

class CostOptimizationObjective(OptimizationObjective):
    """Evaluates and optimizes total system costs"""

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        if not state.treatment_operators:
            return ObjectiveResult(0.0, self.weight, True)

        total_cost = 0.0
        total_processed = 0.0
        
        weighted_costs = {
            CostType.PROCESSING: 1.0,
            CostType.TRANSPORTATION: 1.2,
            CostType.STORAGE: 0.8,
            CostType.LANDFILL: 2.0,
            CostType.OVERFLOW: 2.5,
            CostType.MAINTENANCE: 0.9,
            CostType.ENERGY: 1.1,
        }

        for operator in state.treatment_operators:
            cost_breakdown = operator.cost_tracker.get_cost_breakdown()
            operator_processed = sum(operator.processed_volumes.values())
            total_processed += operator_processed

            # Calculate weighted costs
            for cost_type_str, cost in cost_breakdown.items():
                cost_type = CostType(cost_type_str)
                total_cost += cost * weighted_costs[cost_type]

        # Calculate cost per unit processed
        if total_processed > 0:
            unit_cost = total_cost / total_processed
        else:
            unit_cost = total_cost if total_cost > 0 else 1.0

        # Normalize total cost (higher cost = lower score)
        score = 1.0 / (1.0 + unit_cost / 1000)  # Normalize per 1000 units
        return ObjectiveResult(score, self.weight, True)
