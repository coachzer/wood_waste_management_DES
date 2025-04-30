from typing import Dict, Optional
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
from .base_plotter import BasePlotter
from .plot_utils import (
    setup_axis_labels,
    add_year_demarcations,
    plot_multi_series,
    GRID_ALPHA,
)

class OverflowPlotter(BasePlotter):
    """Plotter for system overflow visualization."""

    def plot_overflow_summary(
        self,
        history: Dict[str, Dict],
        save_path: Optional[str] = None
    ) -> None:
        """Create a comprehensive overflow analysis plot.
        
        Args:
            history: Dictionary containing overflow history data
            save_path: Optional path to save the plot
        """
        # Skip plotting if there's no data (only initial zeros)
        has_data = False
        for key in history:
            if len(history[key]["values"]) > 1:  # More than just the initial [0.0]
                has_data = True
                break
                
        if not has_data:
            print("No overflow data to plot")
            return
        # Create figure with 2x2 grid
        fig = plt.figure(figsize=(15, 12))
        gs = GridSpec(2, 2, figure=fig)
        
        # Get the shared timestamps and interpolate missing values
        all_timestamps = []
        for key in history:
            all_timestamps.extend(history[key]["timestamps"])
        unique_timestamps = sorted(list(set(all_timestamps)))
        
        # Plot 1: Facility overflow volumes
        ax1 = fig.add_subplot(gs[0, 0])
        self._plot_facility_overflow(ax1, self._interpolate_values(history, unique_timestamps, ["generator_overflow", "collector_overflow", "treatment_overflow"]), unique_timestamps)
        
        # Plot 2: Strategy usage
        ax2 = fig.add_subplot(gs[0, 1])
        self._plot_strategy_usage(ax2, self._interpolate_values(history, unique_timestamps, ["landfill_usage", "expand_storage_usage", "emergency_transport_usage", "reduce_intake_usage"]), unique_timestamps)
        
        # Plot 3: Cumulative costs
        ax3 = fig.add_subplot(gs[1, :])
        self._plot_cumulative_costs(ax3, self._interpolate_values(history, unique_timestamps, ["landfill_penalties", "storage_expansion", "emergency_transport", "total_cost"]), unique_timestamps)
        
        # Add overall title
        fig.suptitle("System Overflow Analysis", fontsize=14, y=0.95)
        
        # Save or show plot
        plt.tight_layout()
        self.save_figure(fig, save_path)

    def _interpolate_values(self, history: Dict, timestamps: list, keys: list) -> Dict:
        """Interpolate missing values for each key in history"""
        result = {}
        for key in keys:
            if key in history:
                orig_times = history[key]["timestamps"]
                orig_values = history[key]["values"]
                
                # Create interpolated values array
                new_values = np.zeros(len(timestamps))
                for i, t in enumerate(timestamps):
                    if t in orig_times:
                        idx = orig_times.index(t)
                        new_values[i] = orig_values[idx]
                    else:
                        # Find nearest previous value
                        prev_values = [v for idx, v in zip(orig_times, orig_values) if idx <= t]
                        new_values[i] = prev_values[-1] if prev_values else 0.0
                
                result[key] = {"values": new_values.tolist(), "timestamps": timestamps}
        return result

    def _plot_facility_overflow(self, ax: plt.Axes, history: Dict, timestamps: list) -> None:
        """Plot overflow volumes by facility type."""
        facility_colors = {
            "generator": "#FF9999",  # Light red
            "collector": "#66B2FF",  # Light blue
            "treatment": "#99FF99",  # Light green
        }
        
        facility_data = {
            facility_type: history[f"{facility_type}_overflow"]["values"]
            for facility_type in ["generator", "collector", "treatment"]
            if f"{facility_type}_overflow" in history
        }
        
        plot_multi_series(
            ax=ax,
            timestamps=timestamps,
            series_data=facility_data,
            colors=facility_colors,
            title="Facility Overflow Volumes",
            ylabel="Volume (m³)",
            window=self.window
        )
        
        add_year_demarcations(ax)

    def _plot_strategy_usage(self, ax: plt.Axes, history: Dict, timestamps: list) -> None:
        """Plot overflow strategy usage over time."""
        strategy_colors = {
            "landfill": "#FF0000",        # Red
            "expand_storage": "#00FF00",   # Green
            "emergency_transport": "#0000FF", # Blue
            "reduce_intake": "#FFA500"     # Orange
        }
        
        strategy_data = {
            strategy: history[f"{strategy}_usage"]["values"]
            for strategy in strategy_colors.keys()
            if f"{strategy}_usage" in history
        }
        
        plot_multi_series(
            ax=ax,
            timestamps=timestamps,
            series_data=strategy_data,
            colors=strategy_colors,
            title="Overflow Strategy Usage",
            ylabel="Frequency",
            window=self.window
        )
        
        add_year_demarcations(ax)

    def _plot_cumulative_costs(self, ax: plt.Axes, history: Dict, timestamps: list) -> None:
        """Plot cumulative costs for different overflow handling strategies."""
        strategy_colors = {
            "landfill_penalties": "#FF6B6B",     # Coral red
            "storage_expansion": "#4ECDC4",       # Turquoise
            "emergency_transport": "#45B7D1",     # Sky blue
            "total_cost": "#2C3E50"              # Dark blue
        }
        
        cost_data = {
            cost_type: np.cumsum(history[cost_type]["values"])
            for cost_type in strategy_colors
            if cost_type in history
        }
        
        for name, data in cost_data.items():
            ax.plot(
                timestamps,
                data,
                label=name.replace("_", " ").title(),
                color=strategy_colors[name],
                linewidth=2
            )
        
        setup_axis_labels(
            ax,
            title="Cumulative Overflow Management Costs",
            ylabel="Cost (€)"
        )
        add_year_demarcations(ax)
        ax.legend(loc='upper left')
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
