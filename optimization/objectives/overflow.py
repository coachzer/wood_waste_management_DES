import numpy as np
from typing import Dict, List, Tuple
from optimization.objectives.base import OptimizationObjective, ObjectiveResult
from models.state import SimulationState

class OverflowPenaltyObjective(OptimizationObjective):
    """
    Evaluates overflow penalties across the system.
    
    This objective tracks and penalizes waste overflow events, considering:
    - Total volume of waste overflow
    - Frequency of overflow events
    - System capacity utilization
    - Historical overflow patterns
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._overflow_history: List[Tuple[str, float]] = []
        self._capacity_history: List[float] = []

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate overflow penalties across all entities
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the normalized overflow penalty score
        """
        overflow_by_type = {
            "generator": [],
            "collector": [],
            "treatment": []
        }
        
        total_capacity = 0
        total_current = 0

        # Analyze generators
        generator_stats = self._analyze_generators(
            state.generators, overflow_by_type, total_capacity, total_current
        )
        total_capacity += generator_stats["capacity"]
        total_current += generator_stats["current"]

        # Analyze collectors
        collector_stats = self._analyze_collectors(
            state.collectors, overflow_by_type, total_capacity, total_current
        )
        total_capacity += collector_stats["capacity"]
        total_current += collector_stats["current"]

        # Analyze treatment operators
        treatment_stats = self._analyze_treatment_operators(
            state.treatment_operators, overflow_by_type, total_capacity, total_current
        )
        total_capacity += treatment_stats["capacity"]
        total_current += treatment_stats["current"]

        # Calculate penalties with weights for different facility types
        total_penalty = self._calculate_weighted_penalty(overflow_by_type)

        # Update history
        self._update_history(total_penalty, total_capacity)

        # Calculate normalized penalty relative to system capacity
        if total_capacity > 0:
            normalized_penalty = total_penalty / total_capacity
        else:
            normalized_penalty = total_penalty if total_penalty > 0 else 1.0

        # Calculate risk measure based on current system state
        risk_measure = self._calculate_risk_measure(
            total_current, total_capacity, overflow_by_type
        )

        return ObjectiveResult(
            score=normalized_penalty,
            weight=self.weight,
            should_minimize=self.should_minimize,
            risk_measure=risk_measure
        )

    def _analyze_generators(
        self, generators: list, overflow_by_type: Dict, total_capacity: float,
        total_current: float
    ) -> Dict[str, float]:
        """Analyze overflow and capacity for generators"""
        capacity = 0
        current = 0
        
        for generator in generators:
            overflow = generator.overflow_tracker.total_landfilled
            overflow_by_type["generator"].append(overflow)
            
            capacity += generator.storage_capacity
            current += generator.current_storage

        return {"capacity": capacity, "current": current}

    def _analyze_collectors(
        self, collectors: list, overflow_by_type: Dict, total_capacity: float,
        total_current: float
    ) -> Dict[str, float]:
        """Analyze overflow and capacity for collectors"""
        capacity = 0
        current = 0
        
        for collector in collectors:
            overflow = collector.overflow_tracker.total_landfilled
            overflow_by_type["collector"].append(overflow)
            
            capacity += collector.collection_capacity
            current += sum(collector.collected_waste.values())

        return {"capacity": capacity, "current": current}

    def _analyze_treatment_operators(
        self, operators: list, overflow_by_type: Dict, total_capacity: float,
        total_current: float
    ) -> Dict[str, float]:
        """Analyze overflow and capacity for treatment operators"""
        capacity = 0
        current = 0
        
        for operator in operators:
            overflow = operator.overflow_tracker.total_landfilled
            overflow_by_type["treatment"].append(overflow)
            
            capacity += operator.storage_capacity
            current += operator.current_storage

        return {"capacity": capacity, "current": current}

    def _calculate_weighted_penalty(self, overflow_by_type: Dict[str, List[float]]) -> float:
        """Calculate weighted penalty based on facility type"""
        weights = {
            "generator": 1.0,    # Base weight for generators
            "collector": 1.2,    # Higher penalty for collectors
            "treatment": 1.5     # Highest penalty for treatment facilities
        }
        
        total_penalty = 0.0
        for facility_type, overflows in overflow_by_type.items():
            if overflows:  # Only process if we have overflow data
                total_penalty += sum(overflows) * weights[facility_type]
                
        return total_penalty

    def _calculate_risk_measure(
        self, total_current: float, total_capacity: float,
        overflow_by_type: Dict[str, List[float]]
    ) -> float:
        """
        Calculate risk measure based on current system state and recent overflow history
        """
        # Calculate capacity utilization risk
        utilization_risk = total_current / total_capacity if total_capacity > 0 else 1.0
        
        # Calculate overflow frequency risk
        total_overflows = sum(len(overflows) for overflows in overflow_by_type.values())
        overflow_risk = min(1.0, total_overflows / 10)  # Cap at 1.0
        
        # Combine risks with weights
        risk_measure = 0.7 * utilization_risk + 0.3 * overflow_risk
        
        return risk_measure

    def _update_history(self, penalty: float, capacity: float) -> None:
        """Update historical tracking of overflows and capacity"""
        self._overflow_history.append((penalty, capacity))
        self._capacity_history.append(capacity)
        
        # Keep history bounded
        max_history = 1000
        if len(self._overflow_history) > max_history:
            self._overflow_history = self._overflow_history[-max_history:]
            self._capacity_history = self._capacity_history[-max_history:]

    def __str__(self) -> str:
        return "Overflow Penalty Objective"
