# optimizer.py
from typing import Dict, List
from dataclasses import dataclass
from models.state import SimulationState
from optimization.objectives import OptimizationObjective
from optimization.optimization_history import OptimizationHistory
from optimization.strategies import OptimizationStrategy, OptimizationAction


@dataclass
class OptimizationResult:
    scores: Dict[str, float]
    actions: List[OptimizationAction]
    suggestions: List[str]


class WasteOptimizer:
    def __init__(
        self, objectives: List[OptimizationObjective], strategy: OptimizationStrategy
    ):
        self.objectives = objectives
        self.strategy = strategy
        self.state = SimulationState.get_instance()
        self.history = OptimizationHistory()

    def optimize(self) -> OptimizationResult:
        # Calculate scores
        scores = {}
        for objective in self.objectives:
            result = objective.evaluate(self.state)
            normalized_score = objective.normalize_score(result.score)
            scores[objective.__class__.__name__] = normalized_score * result.weight

        # Generate optimization actions
        actions = self.strategy.generate_actions(scores)

        # Generate suggestions
        suggestions = self._generate_suggestions(scores)

        # Record history
        self.history.record(scores, actions, suggestions)

        # Apply optimizations
        self._apply_optimizations(actions)

        return OptimizationResult(scores, actions, suggestions)

    def _generate_suggestions(self, scores: Dict[str, float]) -> List[str]:
        suggestions = []
        if scores.get("StorageUtilizationObjective", 0) < 0.3:
            suggestions.append("Consider reducing storage capacity")
        return suggestions

    def _apply_optimizations(self, actions: List[OptimizationAction]):
        for action in actions:
            if action.entity_type == "collector":
                for collector in self.state.collectors:
                    if action.entity_id == "all" or action.entity_id == collector.name:
                        # Need to ensure these changes are actually affecting the simulation
                        current_value = getattr(collector, action.parameter)
                        new_value = current_value * action.adjustment
                        setattr(collector, action.parameter, new_value)
                        print(
                            f"Adjusted {collector.name} {action.parameter} from {current_value} to {new_value}"
                        )
            elif action.entity_type == "treatment":
                for operator in self.state.treatment_operators:
                    if action.entity_id == "all" or action.entity_id == operator.name:
                        current_value = getattr(operator, action.parameter)
                        new_value = current_value * action.adjustment
                        setattr(operator, action.parameter, new_value)
                        print(
                            f"Adjusted {operator.name} {action.parameter} from {current_value} to {new_value}"
                        )
