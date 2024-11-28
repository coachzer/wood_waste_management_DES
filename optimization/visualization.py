# visualization.py
import matplotlib.pyplot as plt
from typing import List, Dict

from optimization.optimization_history import OptimizationHistory


class OptimizationVisualizer:
    def __init__(self, history: OptimizationHistory):
        self.history = history

    def create_metric_plot(self, metric_name: str, ax, color: str = "blue"):
        values = self.history.get_metric_history(metric_name)
        timestamps = range(len(values))
        ax.plot(timestamps, values, marker="o", color=color)
        ax.set_title(f"{metric_name} Over Time")
        ax.set_xlabel("Time")
        ax.set_ylabel("Score")
        ax.grid(True)

    def plot_results(self, output_path: str = "optimization_results.png"):
        _, axes = plt.subplots(2, 2, figsize=(15, 10))
        metrics = [
            ("StorageUtilization", "green"),
            ("CollectionEfficiency", "blue"),
            ("EnvironmentalImpact", "red"),
            ("ProcessingEfficiency", "purple"),
        ]

        for (metric, color), ax in zip(metrics, axes.flat):
            self.create_metric_plot(metric, ax, color)

        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
