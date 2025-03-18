import numpy as np
from optimization.objectives.base import OptimizationObjective, ObjectiveResult
from models.state import SimulationState

class StorageUtilizationObjective(OptimizationObjective):
    """
    Evaluates storage utilization and robustness across the system.
    
    This objective balances optimal storage utilization with safety margins,
    considering both the average utilization and its variability across facilities.
    """

    def evaluate(self, state: SimulationState) -> ObjectiveResult:
        """
        Evaluate storage utilization across all facilities
        
        Args:
            state: Current simulation state
            
        Returns:
            ObjectiveResult containing the combined utilization and margin score
        """
        utilizations = []
        margins = []

        # Process generators
        for generator in state.generators:
            if generator.storage_capacity > 0:
                utilization = generator.current_storage / generator.storage_capacity
                margin = (
                    generator.storage_capacity - generator.current_storage
                ) / generator.storage_capacity
                utilizations.append(utilization)
                margins.append(margin)

        # Process treatment operators
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

        # Calculate averages and variability
        avg_utilization = np.mean(utilizations)
        avg_margin = np.mean(margins)

        # Calculate standard deviations to assess system stability
        util_std = np.std(utilizations) if len(utilizations) > 1 else 0
        margin_std = np.std(margins) if len(margins) > 1 else 0

        # Penalize high variability to encourage balanced utilization
        util_score = avg_utilization * (1 - 0.5 * util_std)
        margin_score = avg_margin * (1 - 0.5 * margin_std)

        # Combine scores with weights favoring utilization over margins
        score = 0.7 * util_score + 0.3 * margin_score

        # Track additional metrics in analysis
        analysis = {
            "average_utilization": avg_utilization,
            "average_margin": avg_margin,
            "utilization_std": util_std,
            "margin_std": margin_std,
            "num_facilities": len(utilizations),
            "facilities_near_capacity": sum(1 for u in utilizations if u > 0.9),
            "facilities_underutilized": sum(1 for u in utilizations if u < 0.3)
        }

        # Include risk measure based on facilities near capacity
        risk_measure = sum(u for u in utilizations if u > 0.9) / len(utilizations) if utilizations else 0

        return ObjectiveResult(
            score=score,
            weight=self.weight,
            should_minimize=self.should_minimize,
            risk_measure=risk_measure
        )

    def __str__(self) -> str:
        return "Storage Utilization Objective"
