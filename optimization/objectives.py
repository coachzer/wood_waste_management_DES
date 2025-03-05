from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict
import numpy as np
from optimization.stochastic import ScenarioGenerator, UncertaintySet
from core.cost_tracker import CostType


@dataclass
class ObjectiveResult:
    score: float
    weight: float
    should_minimize: bool
    risk_measure: float = 0.0
    scenarios_evaluated: int = 1


class OptimizationObjective(ABC):
    def __init__(
        self, weight: float, should_minimize: bool, risk_aversion: float = 0.5
    ):
        self.weight = weight
        self.should_minimize = should_minimize
        self.risk_aversion = risk_aversion
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

        scenarios = self.scenario_generator.generate_scenarios()
        scenario_scores = []

        for scenario in scenarios:
            scenario_state = self._apply_scenario(state, scenario)
            result = self.evaluate(scenario_state)
            scenario_scores.append(result.score)

        mean_score = np.mean(scenario_scores)
        var_95 = np.percentile(scenario_scores, 95 if self.should_minimize else 5)
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
        new_state = state.copy()

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
    """Evaluates storage utilization and robustness across the system"""

    def evaluate(self, state) -> ObjectiveResult:
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

        # Combine utilization and margin scores
        avg_utilization = sum(utilizations) / len(utilizations) if utilizations else 0
        avg_margin = sum(margins) / len(margins) if margins else 0

        # Balance between utilization and safety margin
        score = 0.7 * avg_utilization + 0.3 * avg_margin
        return ObjectiveResult(score, self.weight, self.should_minimize)


class CollectionEfficiencyObjective(OptimizationObjective):
    """Evaluates collection efficiency and reliability"""

    def evaluate(self, state) -> ObjectiveResult:
        scores = []
        for collector in state.collectors:
            # Collection efficiency
            collection_rate = (
                sum(collector.collected_waste.values()) / collector.collection_capacity
            )

            # Reliability and operational efficiency
            reliability = collector.efficiency
            cost_factor = 1 / (1 + (collector.transport_cost / 100))

            # Combined score
            score = 0.5 * collection_rate + 0.3 * reliability + 0.2 * cost_factor
            scores.append(score)

        final_score = sum(scores) / len(scores) if scores else 0
        return ObjectiveResult(final_score, self.weight, self.should_minimize)


class OverflowPenaltyObjective(OptimizationObjective):
    """Evaluates overflow penalties across the system"""

    def evaluate(self, state) -> ObjectiveResult:
        total_penalty = 0
        state = SimulationState.get_instance()

        for generator in state.generators:
            total_penalty += generator.overflow_tracker.total_landfilled

        for collector in state.collectors:
            total_penalty += collector.overflow_tracker.total_landfilled

        for operator in state.treatment_operators:
            total_penalty += operator.overflow_tracker.total_landfilled

        return ObjectiveResult(total_penalty, self.weight, self.should_minimize)


class TreatmentEfficiencyObjective(OptimizationObjective):
    """Evaluates treatment efficiency, reliability, and environmental impact"""

    def evaluate(self, state) -> ObjectiveResult:
        scores = []
        for operator in state.treatment_operators:
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
            scores.append(score)

        final_score = sum(scores) / len(scores) if scores else 0
        return ObjectiveResult(final_score, self.weight, self.should_minimize)


class CostOptimizationObjective(OptimizationObjective):
    """Evaluates and optimizes total system costs"""

    def evaluate(self, state) -> ObjectiveResult:
        total_cost = 0.0
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

            # Sum weighted costs
            for cost_type_str, cost in cost_breakdown.items():
                cost_type = CostType(cost_type_str)
                total_cost += cost * weighted_costs[cost_type]

        # Normalize total cost (higher cost = lower score)
        score = 1.0 / (1.0 + total_cost / 1000)  # Normalize per 1000 units
        return ObjectiveResult(score, self.weight, True)  # should_minimize=True
