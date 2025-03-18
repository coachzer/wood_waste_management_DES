import numpy as np
from optimization.objectives.base import OptimizationObjective, ObjectiveResult
from models.state import SimulationState

class CollectionEfficiencyObjective(OptimizationObjective):
    """
    Evaluates collection efficiency and reliability across the system.
    
    This objective considers multiple factors:
    - Collection rate relative to capacity
    - Operational reliability
    - Cost efficiency of collection operations
    - System-wide collection performance
    """

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate collection efficiency across all collectors
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the combined efficiency score
        """
        if not state.collectors:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        scores = []
        total_capacity = 0
        total_collected = 0
        cost_factors = []
        reliability_scores = []

        for collector in state.collectors:
            # Skip collectors with no capacity
            capacity = collector.collection_capacity
            if capacity <= 0:
                continue
                
            # Calculate collection rate
            collection_amount = sum(collector.collected_waste.values())
            collection_rate = collection_amount / capacity
            
            # Track totals for system-wide metrics
            total_capacity += capacity
            total_collected += collection_amount

            # Calculate cost efficiency
            cost_factor = 1 / (1 + (collector.transport_cost / 100))
            cost_factors.append(cost_factor)

            # Track reliability
            reliability = collector.efficiency
            reliability_scores.append(reliability)

            # Combined score for this collector
            score = self._calculate_collector_score(
                collection_rate, reliability, cost_factor
            )
            scores.append(score)

        if not scores:
            return ObjectiveResult(0.0, self.weight, self.should_minimize)

        # Calculate system-wide collection rate
        system_rate = total_collected / total_capacity if total_capacity > 0 else 0

        # Calculate variability in performance
        score_std = np.std(scores) if len(scores) > 1 else 0
        reliability_std = np.std(reliability_scores) if len(reliability_scores) > 1 else 0

        # Penalize high variability
        avg_score = np.mean(scores) * (1 - 0.3 * score_std)
        system_score = system_rate * (1 - 0.3 * reliability_std)

        # Combine individual and system-wide scores
        final_score = 0.7 * avg_score + 0.3 * system_score

        # Calculate risk measure based on reliability
        risk_measure = 1 - min(reliability_scores) if reliability_scores else 1.0

        # Track analysis metrics
        self._record_analysis(
            scores=scores,
            system_rate=system_rate,
            cost_factors=cost_factors,
            reliability_scores=reliability_scores,
            score_std=score_std,
            reliability_std=reliability_std
        )

        return ObjectiveResult(
            score=final_score,
            weight=self.weight,
            should_minimize=self.should_minimize,
            risk_measure=risk_measure
        )

    def _calculate_collector_score(
        self, collection_rate: float, reliability: float, cost_factor: float
    ) -> float:
        """Calculate combined score for a single collector"""
        weights = {
            'collection_rate': 0.5,  # Prioritize actual collection performance
            'reliability': 0.3,      # Give significant weight to reliability
            'cost': 0.2             # Consider cost efficiency but with lower priority
        }
        
        return (
            weights['collection_rate'] * collection_rate +
            weights['reliability'] * reliability +
            weights['cost'] * cost_factor
        )

    def _record_analysis(
        self,
        scores: list,
        system_rate: float,
        cost_factors: list,
        reliability_scores: list,
        score_std: float,
        reliability_std: float
    ) -> None:
        """Record detailed analysis metrics"""
        self.last_analysis = {
            "average_score": np.mean(scores),
            "score_std": score_std,
            "system_collection_rate": system_rate,
            "average_cost_factor": np.mean(cost_factors),
            "average_reliability": np.mean(reliability_scores),
            "reliability_std": reliability_std,
            "num_collectors": len(scores),
            "collectors_below_threshold": sum(1 for s in scores if s < 0.6),
            "high_performing_collectors": sum(1 for s in scores if s > 0.8)
        }

    def __str__(self) -> str:
        return "Collection Efficiency Objective"
