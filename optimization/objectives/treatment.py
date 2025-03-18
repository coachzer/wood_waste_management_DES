import numpy as np
from typing import Dict, List, Tuple
from optimization.objectives.base import OptimizationObjective, ObjectiveResult
from models.state import SimulationState

class TreatmentEfficiencyObjective(OptimizationObjective):
    """
    Evaluates treatment efficiency, reliability, and environmental impact.
    
    This objective considers multiple factors:
    - Processing efficiency of treatment operations
    - Storage utilization and management
    - Energy efficiency of treatment processes
    - Environmental impact of operations
    - Overall system reliability
    
    The objective balances these factors to optimize treatment operations while
    maintaining environmental standards and operational efficiency.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._efficiency_history: List[float] = []
        self._energy_history: List[float] = []
        self._env_impact_history: List[str] = []

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate treatment efficiency across all operators
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the combined efficiency score
        """
        if not state.treatment_operators:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        operator_scores = []
        operator_weights = []
        total_capacity = 0.0
        efficiency_data = []
        energy_data = []
        environmental_data = []

        for operator in state.treatment_operators:
            # Skip operators with no capacity
            if operator.storage_capacity <= 0:
                continue
                
            total_capacity += operator.storage_capacity
            
            # Calculate component scores
            processing_score = self._calculate_processing_score(operator)
            storage_score = self._calculate_storage_score(operator)
            energy_score = self._calculate_energy_score(operator)
            environmental_score = self._calculate_environmental_score(operator)
            
            # Track metrics for analysis
            efficiency_data.append(processing_score)
            energy_data.append(energy_score)
            environmental_data.append(environmental_score)
            
            # Calculate combined score with weights
            score = self._combine_scores(
                processing_score,
                storage_score,
                energy_score,
                environmental_score
            )
            
            # Weight by capacity
            weight = operator.storage_capacity / total_capacity if total_capacity > 0 else 0
            operator_scores.append(score)
            operator_weights.append(weight)

        if not operator_scores:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        # Calculate weighted average score
        final_score = np.average(operator_scores, weights=operator_weights)
        
        # Update historical tracking
        self._update_history(efficiency_data, energy_data, environmental_data)

        # Calculate risk measure based on variability and environmental impact
        risk_measure = self._calculate_risk_measure(
            efficiency_data, energy_data, environmental_data
        )

        return ObjectiveResult(
            score=final_score,
            weight=self.weight,
            should_minimize=self.should_minimize,
            risk_measure=risk_measure
        )

    def _calculate_processing_score(self, operator) -> float:
        """Calculate processing efficiency score"""
        base_score = operator.conversion_rate
        
        # Consider processing time efficiency
        time_factor = 1.0
        if hasattr(operator, 'processing_time') and operator.processing_time > 0:
            time_factor = 1.0 / (1.0 + operator.processing_time / 24.0)  # Normalize to daily basis
            
        return base_score * time_factor

    def _calculate_storage_score(self, operator) -> float:
        """Calculate storage efficiency score"""
        # Calculate storage utilization
        utilization = operator.current_storage / operator.storage_capacity
        
        # Penalize both under and over-utilization
        optimal_utilization = 0.7  # Target 70% utilization
        deviation = abs(utilization - optimal_utilization)
        
        # Convert to score (1.0 is best, 0.0 is worst)
        return max(0.0, 1.0 - deviation)

    def _calculate_energy_score(self, operator) -> float:
        """Calculate energy efficiency score"""
        # Higher score for lower energy consumption
        return 1.0 / (1.0 + operator.energy_consumption)

    def _calculate_environmental_score(self, operator) -> float:
        """Calculate environmental impact score"""
        impact_scores = {
            "Low": 0.9,
            "Moderate": 0.6,
            "High": 0.3,
            None: 0.5  # Default score
        }
        return impact_scores.get(operator.environmental_impact, 0.5)

    def _combine_scores(
        self,
        processing_score: float,
        storage_score: float,
        energy_score: float,
        environmental_score: float
    ) -> float:
        """Combine individual scores into final score"""
        weights = {
            "processing": 0.4,  # Highest weight for core processing efficiency
            "storage": 0.3,     # Important for operational stability
            "energy": 0.2,      # Significant but lower priority
            "environmental": 0.1 # Base consideration for environmental impact
        }
        
        return (
            weights["processing"] * processing_score +
            weights["storage"] * storage_score +
            weights["energy"] * energy_score +
            weights["environmental"] * environmental_score
        )

    def _update_history(
        self,
        efficiency_data: List[float],
        energy_data: List[float],
        environmental_data: List[str]
    ) -> None:
        """Update historical tracking of performance metrics"""
        if efficiency_data:
            self._efficiency_history.append(np.mean(efficiency_data))
        if energy_data:
            self._energy_history.append(np.mean(energy_data))
        if environmental_data:
            self._env_impact_history.append(max(environmental_data))
            
        # Keep history bounded
        max_history = 1000
        self._efficiency_history = self._efficiency_history[-max_history:]
        self._energy_history = self._energy_history[-max_history:]
        self._env_impact_history = self._env_impact_history[-max_history:]

    def _calculate_risk_measure(
        self,
        efficiency_data: List[float],
        energy_data: List[float],
        environmental_data: List[str]
    ) -> float:
        """Calculate risk measure based on current performance"""
        risks = []
        
        # Efficiency variability risk
        if len(efficiency_data) > 1:
            efficiency_std = np.std(efficiency_data)
            risks.append(min(1.0, efficiency_std))
            
        # Energy consumption risk
        if energy_data:
            energy_risk = 1.0 - np.mean(energy_data)  # Higher energy use = higher risk
            risks.append(energy_risk)
            
        # Environmental impact risk
        impact_risks = {"Low": 0.2, "Moderate": 0.5, "High": 0.8}
        env_risks = [impact_risks.get(impact, 0.5) for impact in environmental_data]
        if env_risks:
            risks.append(max(env_risks))
            
        return np.mean(risks) if risks else 0.5

    def __str__(self) -> str:
        return "Treatment Efficiency Objective"
