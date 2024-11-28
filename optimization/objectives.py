# objectives.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
import random
from typing import List
from models.enums import WasteType


@dataclass
class ObjectiveResult:
    score: float
    weight: float
    should_minimize: bool


class OptimizationObjective(ABC):
    def __init__(self, weight: float, should_minimize: bool):
        self.weight = weight
        self.should_minimize = should_minimize

    @abstractmethod
    def evaluate(self, state) -> ObjectiveResult:
        pass

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
        # Add some randomness to avoid static scores
        score += random.uniform(-0.05, 0.05)
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
