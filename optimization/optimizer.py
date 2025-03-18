from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from models.state import SimulationState
from optimization.objectives import OptimizationObjective
from optimization.optimization_history import OptimizationHistory
from optimization.strategies import OptimizationStrategy, OptimizationAction
from optimization.entity_params import (
    CollectorParams,
    TreatmentParams,
    get_param_name,
    validate_adjustment
)

@dataclass
class OptimizationResult:
    """
    Result of an optimization iteration
    
    Args:
        scores: Dictionary mapping objective names to their scores
        actions: List of optimization actions that were generated
        suggestions: List of suggestions for manual optimization
    """
    scores: Dict[str, float]
    actions: List[OptimizationAction]
    suggestions: List[str]

class WasteOptimizer:
    """
    Optimizes the waste management system by evaluating objectives and applying optimization actions
    
    Args:
        objectives: List of optimization objectives to evaluate
        strategy: Strategy to use for generating optimization actions
        min_improvement_threshold: Minimum score that triggers improvement suggestions
    """
    def __init__(
        self,
        objectives: List[OptimizationObjective],
        strategy: OptimizationStrategy,
        min_improvement_threshold: float = 0.7
    ):
        self.objectives = objectives
        self.strategy = strategy
        self.min_improvement_threshold = min_improvement_threshold
        self.state = SimulationState.get_instance()
        self.history = OptimizationHistory()

    def optimize(self) -> OptimizationResult:
        """
        Perform one iteration of optimization
        
        Returns:
            OptimizationResult containing scores, actions, and suggestions
        """
        # Calculate scores with detailed analysis
        scores, analysis = self._evaluate_objectives()

        # Generate optimization actions based on scores
        actions = self.strategy.generate_actions(scores)

        # Generate suggestions based on detailed analysis
        suggestions = self._generate_suggestions(scores, analysis)

        # Record history
        self.history.record(scores, actions, suggestions)

        # Apply optimizations with validation
        self._apply_optimizations(actions)

        return OptimizationResult(scores, actions, suggestions)

    def _evaluate_objectives(self) -> Tuple[Dict[str, float], Dict[str, Dict]]:
        """
        Evaluate all objectives and provide detailed analysis
        
        Returns:
            Tuple containing:
            - Dictionary of objective scores
            - Dictionary of detailed analysis for each objective
        """
        scores = {}
        analysis = {}
        
        for objective in self.objectives:
            result = objective.evaluate(self.state)
            normalized_score = objective.normalize_score(result.score)
            weighted_score = normalized_score * result.weight
            scores[objective.__class__.__name__] = weighted_score
            
            # Store detailed analysis
            analysis[objective.__class__.__name__] = {
                "raw_score": result.score,
                "normalized_score": normalized_score,
                "weight": result.weight,
                "weighted_score": weighted_score,
                "should_minimize": result.should_minimize,
                "risk_measure": result.risk_measure,
                "scenarios_evaluated": result.scenarios_evaluated
            }
        
        return scores, analysis

    def _generate_suggestions(
        self, scores: Dict[str, float], analysis: Dict[str, Dict]
    ) -> List[str]:
        """
        Generate optimization suggestions based on scores and detailed analysis
        
        Args:
            scores: Dictionary of objective scores
            analysis: Dictionary of detailed analysis for each objective
            
        Returns:
            List of suggestions for improving system performance
        """
        suggestions = []

        # Storage utilization suggestions
        storage_score = scores.get("StorageUtilizationObjective", 1.0)
        if storage_score < 0.3:
            suggestions.append("Critical: Consider reducing storage capacity to improve efficiency")
        elif storage_score < 0.5:
            suggestions.append("Warning: Storage utilization is below optimal levels")
        elif storage_score > 0.9:
            suggestions.append("Warning: Storage capacity is near maximum, consider expansion")

        # Collection efficiency suggestions
        collection_score = scores.get("CollectionEfficiencyObjective", 1.0)
        if collection_score < self.min_improvement_threshold:
            if collection_score < 0.3:
                suggestions.append("Critical: Collection efficiency requires immediate attention")
                suggestions.append("Consider adjusting collection routes or adding collectors")
            else:
                suggestions.append("Consider optimizing collection schedules")

        # Treatment efficiency suggestions
        treatment_score = scores.get("TreatmentEfficiencyObjective", 1.0)
        if treatment_score < self.min_improvement_threshold:
            suggestions.extend(self._generate_treatment_suggestions(treatment_score))

        # Cost optimization suggestions
        if (cost_score := scores.get("CostOptimizationObjective", 1.0)) < self.min_improvement_threshold:
            suggestions.extend(self._generate_cost_suggestions(cost_score, analysis))

        return suggestions

    def _generate_treatment_suggestions(self, score: float) -> List[str]:
        """Generate treatment-specific optimization suggestions"""
        suggestions = []
        if score < 0.3:
            suggestions.append("Critical: Treatment efficiency is severely impacted")
            suggestions.append("Review treatment operator configurations and maintenance schedules")
        elif score < 0.5:
            suggestions.append("Consider upgrading treatment equipment or processes")
        else:
            suggestions.append("Monitor treatment processes for potential improvements")
        return suggestions

    def _generate_cost_suggestions(self, score: float, analysis: Dict[str, Dict]) -> List[str]:
        """Generate cost-specific optimization suggestions"""
        suggestions = []
        if score < 0.3:
            suggestions.append("Critical: Operating costs are significantly higher than optimal")
            suggestions.append("Review all cost centers for potential optimization")
        elif score < 0.5:
            suggestions.append("Consider implementing cost reduction measures")
            if analysis["CostOptimizationObjective"]["risk_measure"] > 0.7:
                suggestions.append("High cost volatility detected - consider risk mitigation strategies")
        return suggestions

    def _apply_optimizations(self, actions: List[OptimizationAction]):
        """
        Apply optimization actions to the system with validation
        
        Args:
            actions: List of optimization actions to apply
        """
        for action in actions:
            try:
                if action.entity_type == "collector":
                    self._adjust_entities(action, self.state.collectors)
                elif action.entity_type == "treatment":
                    self._adjust_entities(action, self.state.treatment_operators)
            except Exception as e:
                print(f"Failed to apply optimization action: {str(e)}")
    
    def _adjust_entities(self, action: OptimizationAction, entities):
        """
        Apply an optimization action to the specified entities with validation
        
        Args:
            action: The optimization action to apply
            entities: List of entities to apply the action to
        """
        param_name = get_param_name(action.parameter)
        
        for entity in entities:
            if action.entity_id == "all" or action.entity_id == entity.name:
                try:
                    current_value = getattr(entity, param_name)
                    new_value = current_value * action.adjustment
                    # Validate the new value before applying
                    validated_value = validate_adjustment(action.parameter, new_value)
                    setattr(entity, param_name, validated_value)
                except AttributeError:
                    print(f"Invalid parameter {param_name} for entity {entity.name}")
                except ValueError as e:
                    print(f"Validation error for {entity.name}: {str(e)}")
