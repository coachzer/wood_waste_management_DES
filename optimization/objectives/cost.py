import numpy as np
from typing import Any, Dict, List
from optimization.objectives.base import OptimizationObjective, ObjectiveResult
from models.state import SimulationState
from config.cost_config import CostType

class CostOptimizationObjective(OptimizationObjective):
    """
    Evaluates and optimizes total system costs.
    
    This objective considers various cost factors:
    - Processing costs for waste treatment
    - Transportation costs for waste collection
    - Storage costs for facility operations
    - Landfill costs for overflow handling
    - Energy costs for equipment operation
    - Maintenance costs for facilities
    
    Each cost type is weighted according to its impact and priority in the system.
    The objective aims to minimize total operational costs while maintaining
    system efficiency and environmental standards.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default to minimizing costs
        self.should_minimize = True
        
        # Historical tracking of costs
        self._cost_history: List[Dict[CostType, float]] = []
        self._utilization_history: List[float] = []
        
        # Configure cost weights
        self._cost_weights = {
            CostType.PROCESSING: 1.0,      # Base processing costs
            CostType.TRANSPORTATION: 1.2,   # Higher weight due to fuel costs
            CostType.STORAGE: 0.8,         # Lower weight for storage
            CostType.LANDFILL: 2.0,        # High penalty for landfill use
            CostType.OVERFLOW: 2.5,        # Highest penalty for overflow
            CostType.MAINTENANCE: 0.9,      # Regular maintenance costs
            CostType.ENERGY: 1.1,          # Energy consumption costs
        }

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate total system costs across all operators
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the normalized cost score
        """
        if not state.treatment_operators:
            return ObjectiveResult(0.0, self.weight, True)

        total_cost = 0.0
        total_processed = 0.0
        cost_breakdown = {cost_type: 0.0 for cost_type in CostType}
        operator_metrics = []

        # Analyze each operator's costs
        for operator in state.treatment_operators:
            operator_costs = operator.cost_tracker.get_cost_breakdown()
            operator_processed = sum(operator.processed_volumes.values())
            
            metrics = self._analyze_operator_costs(
                operator_costs, operator_processed
            )
            operator_metrics.append(metrics)
            
            # Update totals
            total_processed += operator_processed
            self._update_cost_breakdown(cost_breakdown, operator_costs)
            total_cost += metrics["weighted_total"]

        # Calculate unit costs and efficiency metrics
        if total_processed > 0:
            unit_cost = total_cost / total_processed
        else:
            unit_cost = total_cost if total_cost > 0 else 1.0

        # Update historical tracking
        self._update_history(cost_breakdown, total_processed)

        # Calculate risk measure
        risk_measure = self._calculate_risk_measure(
            operator_metrics, unit_cost, total_processed
        )

        # Normalize score (higher cost = lower score)
        score = 1.0 / (1.0 + unit_cost / 1000)  # Normalize per 1000 units

        return ObjectiveResult(
            score=score,
            weight=self.weight,
            should_minimize=True,
            risk_measure=risk_measure
        )

    def _analyze_operator_costs(
        self, operator_costs: Dict[str, float], processed_volume: float
    ) -> Dict[str, float]:
        """Analyze costs for a single operator"""
        weighted_total = 0.0
        raw_total = 0.0
        
        for cost_type_str, cost in operator_costs.items():
            cost_type = CostType(cost_type_str)
            weight = self._cost_weights[cost_type]
            weighted_total += cost * weight
            raw_total += cost

        return {
            "weighted_total": weighted_total,
            "raw_total": raw_total,
            "processed_volume": processed_volume,
            "unit_cost": raw_total / processed_volume if processed_volume > 0 else float('inf')
        }

    def _update_cost_breakdown(
        self, breakdown: Dict[CostType, float], operator_costs: Dict[str, float]
    ) -> None:
        """Update the cost breakdown with an operator's costs"""
        for cost_type_str, cost in operator_costs.items():
            cost_type = CostType(cost_type_str)
            breakdown[cost_type] += cost * self._cost_weights[cost_type]

    def _update_history(
        self, cost_breakdown: Dict[CostType, float], total_processed: float
    ) -> None:
        """Update historical tracking of costs and utilization"""
        self._cost_history.append(dict(cost_breakdown))
        
        # Track processing volume as a utilization metric
        max_expected_volume = 1000  # Baseline expected volume
        utilization = min(1.0, total_processed / max_expected_volume)
        self._utilization_history.append(utilization)
        
        # Keep history bounded
        max_history = 1000
        if len(self._cost_history) > max_history:
            self._cost_history = self._cost_history[-max_history:]
            self._utilization_history = self._utilization_history[-max_history:]

    def _calculate_risk_measure(
        self,
        operator_metrics: List[Dict[str, float]],
        unit_cost: float,
        total_processed: float
    ) -> float:
        """Calculate risk measure based on cost patterns and efficiency"""
        risks = []
        
        # Cost variability risk
        if operator_metrics:
            unit_costs = [m["unit_cost"] for m in operator_metrics if m["unit_cost"] != float('inf')]
            if unit_costs:
                cost_std = np.std(unit_costs)
                cost_mean = np.mean(unit_costs)
                cost_variability_risk = min(1.0, cost_std / cost_mean if cost_mean > 0 else 1.0)
                risks.append(cost_variability_risk)
        
        # Utilization risk
        if self._utilization_history:
            recent_utilization = np.mean(self._utilization_history[-10:])
            utilization_risk = 1.0 - recent_utilization
            risks.append(utilization_risk)
        
        # Cost efficiency risk
        target_unit_cost = 500  # Target cost per unit
        cost_efficiency_risk = min(1.0, unit_cost / target_unit_cost)
        risks.append(cost_efficiency_risk)
        
        return np.mean(risks) if risks else 0.5

    def get_cost_analysis(self) -> Dict[str, Any]:
        """Get detailed analysis of cost patterns"""
        if not self._cost_history:
            return {}
            
        recent_costs = self._cost_history[-10:]
        analysis = {}
        
        for cost_type in CostType:
            costs = [costs.get(cost_type, 0.0) for costs in recent_costs]
            analysis[cost_type.name] = {
                "average": np.mean(costs),
                "std": np.std(costs) if len(costs) > 1 else 0.0,
                "trend": self._calculate_trend(costs)
            }
            
        return analysis

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from a series of values"""
        if len(values) < 2:
            return "stable"
            
        slope = np.polyfit(range(len(values)), values, 1)[0]
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"

    def __str__(self) -> str:
        return "Cost Optimization Objective"
