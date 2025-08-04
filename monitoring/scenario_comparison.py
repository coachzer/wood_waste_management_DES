import os
from typing import Dict, List
from .visualization.storage_visualization import create_storage_heatmaps
from .visualization.temporal_comparison import create_temporal_comparisons
from .visualization.summary_visualization import (
    create_cost_impact_comparison,
    create_summary_dashboard
)

class ScenarioComparison:
    def __init__(self, results: List[Dict]):
        self.results = results
        self.output_dir = "plots/scenario_comparison"
        os.makedirs(self.output_dir, exist_ok=True)

    def create_storage_heatmaps(self):
        """Create heatmap visualizations of storage utilization"""
        create_storage_heatmaps(self.results, self.output_dir)

    def create_temporal_comparison(self):
        """Create time-series comparison plots for key metrics"""
        create_temporal_comparisons(self.results, self.output_dir)

    def create_cost_impact_comparison(self):
        """Create bar charts comparing cost and environmental impact breakdowns"""
        create_cost_impact_comparison(self.results, self.output_dir)

    def create_summary_dashboard(self):
        """Create a comprehensive dashboard with key metrics"""
        create_summary_dashboard(self.results, self.output_dir)