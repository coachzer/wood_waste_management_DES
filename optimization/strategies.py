# optimization/strategies.py
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class OptimizationAction:
    entity_type: str  # 'generator', 'collector', or 'treatment'
    entity_id: str
    parameter: str
    adjustment: float


class OptimizationStrategy:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def generate_actions(self, scores: Dict[str, float]) -> List[OptimizationAction]:
        actions = []
        if scores.get("StorageUtilizationObjective", 0) < self.threshold:
            actions.append(
                OptimizationAction(
                    entity_type="collector",
                    entity_id="all",
                    parameter="collection_frequency",
                    adjustment=0.8,  # Reduce frequency by 20%
                )
            )
            actions.append(
                OptimizationAction(
                    entity_type="treatment",
                    entity_id="all",
                    parameter="processing_time",
                    adjustment=0.8,  # Increase processing speed by reducing time by 20%
                )
            )

        if scores.get("CollectionEfficiencyObjective", 0) < self.threshold:
            actions.append(
                OptimizationAction(
                    entity_type="collector",
                    entity_id="all",
                    parameter="efficiency",
                    adjustment=1.2,  # Increase efficiency by 20%
                )
            )

        if scores.get("TreatmentEfficiencyObjective", 0) < self.threshold:
            actions.append(
                OptimizationAction(
                    entity_type="treatment",
                    entity_id="all",
                    parameter="conversion_rate",
                    adjustment=1.1,  # Increase conversion rate by 10%
                )
            )
        return actions
