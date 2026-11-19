import os
from typing import Dict, List
from config.constants import SCENARIO_COMPARISON_PLOTS_DIR
from .storage_visualization import create_storage_heatmaps
from .temporal_comparison import create_temporal_comparisons
from .summary_visualization import (
    create_cost_impact_comparison,
    create_summary_dashboard
)


def create_scenario_comparison(results: List[Dict]) -> None:
    """Draw every grid-mode comparison figure into SCENARIO_COMPARISON_PLOTS_DIR."""
    os.makedirs(SCENARIO_COMPARISON_PLOTS_DIR, exist_ok=True)
    create_storage_heatmaps(results, SCENARIO_COMPARISON_PLOTS_DIR)
    create_temporal_comparisons(results, SCENARIO_COMPARISON_PLOTS_DIR)
    create_cost_impact_comparison(results, SCENARIO_COMPARISON_PLOTS_DIR)
    create_summary_dashboard(results, SCENARIO_COMPARISON_PLOTS_DIR)
