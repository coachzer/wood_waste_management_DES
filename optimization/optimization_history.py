# optimization_history.py
from dataclasses import dataclass
from typing import Dict, List
import time


@dataclass
class OptimizationSnapshot:
    timestamp: float
    scores: Dict[str, float]
    actions: List[dict]  # Add this field
    suggestions: List[str]  # Add this field


class OptimizationHistory:
    def __init__(self):
        self.snapshots: List[OptimizationSnapshot] = []

    def record(
        self, scores: Dict[str, float], actions: List[dict], suggestions: List[str]
    ):
        snapshot = OptimizationSnapshot(
            timestamp=time.time(),
            scores=scores,
            actions=actions,
            suggestions=suggestions,
        )
        self.snapshots.append(snapshot)

    def get_metric_history(self, metric_name: str) -> List[float]:
        return [snap.scores.get(metric_name, 0) for snap in self.snapshots]
