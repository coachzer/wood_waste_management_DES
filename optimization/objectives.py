from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict
import numpy as np
from optimization.stochastic import ScenarioGenerator, UncertaintySet


@dataclass
class ObjectiveResult:
    score: float
    weight: float
    should_minimize: bool
    risk_measure: float = 0.0  # Value-at-Risk or other risk measures
    scenarios_evaluated: int = 1


class OptimizationObjective(ABC):

    def __init__(
        self, weight: float, should_minimize: bool, risk_aversion: float = 0.5
    ):
        self.weight = weight
        self.should_minimize = should_minimize
        self.risk_aversion = risk_aversion  # Risk aversion parameter (0-1)
        self.scenario_generator = None

    def set_scenario_generator(self, scenario_generator: ScenarioGenerator):
        """Set the scenario generator for stochastic evaluation"""
        self.scenario_generator = scenario_generator

    @abstractmethod
    def evaluate(self, state) -> ObjectiveResult:
        """Evaluate the objective for a given state"""
        pass

    def evaluate_stochastic(self, state) -> ObjectiveResult:
        """Evaluate the objective across multiple scenarios"""
        if not self.scenario_generator:
            return self.evaluate(state)

        # Generate scenarios
        scenarios = self.scenario_generator.generate_scenarios()
        scenario_scores = []

        # Evaluate each scenario
        for scenario in scenarios:
            # Create a copy of state with scenario parameters
            scenario_state = self._apply_scenario(state, scenario)
            result = self.evaluate(scenario_state)
            scenario_scores.append(result.score)

        # Calculate statistics
        mean_score = np.mean(scenario_scores)
        var_95 = np.percentile(scenario_scores, 95 if self.should_minimize else 5)

        # Combine expected value and risk measure
        final_score = (
            1 - self.risk_aversion
        ) * mean_score + self.risk_aversion * var_95

        return ObjectiveResult(
            score=final_score,
            weight=self.weight,
            should_minimize=self.should_minimize,
            risk_measure=var_95,
            scenarios_evaluated=len(scenarios),
        )

    def _apply_scenario(self, state, scenario: Dict) -> "SimulationState":
        """Apply scenario parameters to create a new state"""
        # Create a shallow copy of state
        new_state = state.copy()

        # Apply scenario parameters
        if "waste_generation" in scenario:
            for generator in new_state.generators:
                for waste_type, rate in scenario["waste_generation"].items():
                    if waste_type in generator.waste_generation_rates:
                        generator.waste_generation_rates[waste_type] *= rate

        if "collection_efficiency" in scenario:
            for collector in new_state.collectors:
                collector.efficiency *= scenario["collection_efficiency"]

        if "treatment_conversion" in scenario:
            for operator in new_state.treatment_operators:
                for waste_type, rate in scenario["treatment_conversion"].items():
                    if waste_type in operator.transformations:
                        operator.transformations[
                            waste_type
                        ].conversion_efficiency *= rate

        return new_state

    def normalize_score(self, score: float) -> float:
        return 1 / (1 + score) if self.should_minimize else score


class StorageUtilizationObjective(OptimizationObjective):
    def evaluate(self, state) -> ObjectiveResult:
        utilizations = []
        for generator in state.generators:
            if generator.storage_capacity > 0:  # Avoid division by zero
                utilization = generator.current_storage / generator.storage_capacity
                utilizations.append(utilization)

        score = sum(utilizations) / len(utilizations) if utilizations else 0
        return ObjectiveResult(score, self.weight, self.should_minimize)


class CollectionEfficiencyObjective(OptimizationObjective):
    def evaluate(self, state) -> ObjectiveResult:
        efficiency_scores = [
            collector.efficiency
            * (sum(collector.collected_waste.values()) / collector.collection_capacity)
            for collector in state.collectors
        ]
        score = sum(efficiency_scores) / len(efficiency_scores)
        return ObjectiveResult(score, self.weight, self.should_minimize)


class TreatmentEfficiencyObjective(OptimizationObjective):
    def evaluate(self, state) -> ObjectiveResult:
        efficiency_scores = [
            operator.conversion_rate
            * (1 - operator.current_storage / operator.storage_capacity)
            for operator in state.treatment_operators
        ]
        score = sum(efficiency_scores) / len(efficiency_scores)
        return ObjectiveResult(score, self.weight, self.should_minimize)


class RobustStorageObjective(OptimizationObjective):
    """Evaluates storage robustness against demand uncertainty"""

    def evaluate(self, state) -> ObjectiveResult:
        storage_margins = []
        for operator in state.treatment_operators:
            # Calculate margin between current storage and capacity
            margin = operator.storage_capacity - operator.current_storage
            margin_ratio = (
                margin / operator.storage_capacity
                if operator.storage_capacity > 0
                else 0
            )
            storage_margins.append(margin_ratio)

        for generator in state.generators:
            margin = generator.storage_capacity - generator.current_storage
            margin_ratio = (
                margin / generator.storage_capacity
                if generator.storage_capacity > 0
                else 0
            )
            storage_margins.append(margin_ratio)

        score = sum(storage_margins) / len(storage_margins) if storage_margins else 0
        return ObjectiveResult(score, self.weight, self.should_minimize)


class ReliabilityObjective(OptimizationObjective):
    """Evaluates system reliability considering equipment failures and uncertainties"""

    def evaluate(self, state) -> ObjectiveResult:
        reliability_scores = []

        # Treatment operator reliability
        for operator in state.treatment_operators:
            # Consider both storage and processing reliability
            storage_reliability = min(
                1.0,
                operator.storage_capacity / (operator.initial_storage_capacity * 1.2),
            )
            processing_reliability = operator.conversion_rate
            reliability_scores.append(
                (storage_reliability + processing_reliability) / 2
            )

        # Collection system reliability
        for collector in state.collectors:
            collection_reliability = collector.efficiency
            reliability_scores.append(collection_reliability)

        score = (
            sum(reliability_scores) / len(reliability_scores)
            if reliability_scores
            else 0
        )
        return ObjectiveResult(score, self.weight, self.should_minimize)


class StochasticCostObjective(OptimizationObjective):
    """Evaluates system costs considering uncertainties"""

    def evaluate(self, state) -> ObjectiveResult:
        total_cost = 0.0

        # Operational costs
        for operator in state.treatment_operators:
            # Base operational cost
            cost = operator.operational_costs
            # Storage cost proportional to utilization
            storage_cost = cost * (operator.current_storage / operator.storage_capacity)
            # Energy cost
            energy_cost = operator.energy_consumption * operator.total_products_created
            total_cost += cost + storage_cost + energy_cost

        # Transportation costs
        for collector in state.collectors:
            # Cost proportional to collection amount and distance (simplified)
            collection_cost = (
                sum(collector.collected_waste.values()) * 10
            )  # Assume 10 cost units per volume
            total_cost += collection_cost

        # Environmental impact costs - convert string values to numbers
        def get_env_impact_value(impact):
            impact_map = {"Low": 1, "Moderate": 2, "High": 3}
            return impact_map.get(impact, 0)  # default to 0 if unknown value

        env_cost = sum(
            get_env_impact_value(gen.environmental_impact) for gen in state.generators
        )
        env_cost += sum(
            get_env_impact_value(op.environmental_impact)
            for op in state.treatment_operators
        )
        total_cost += env_cost * 50  # Scale factor for environmental impact cost

        return ObjectiveResult(total_cost, self.weight, self.should_minimize)
