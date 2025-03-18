from typing import Dict, Any
import numpy as np
import matplotlib.pyplot as plt
from ..visualizations.plot_utils import (
    VOLUME_LABEL,
    GRID_ALPHA,
    setup_axis_labels,
    add_moving_average_plot,
    plot_multi_series,
)
from .base_plotter import BasePlotter
from .production_plots import ProductionPlotter
from .waste_plots import WastePlotter

class EfficiencyPlotter(BasePlotter):
    """Handles plotting of efficiency-related metrics"""
    
    def __init__(self):
        super().__init__()
        self.production_plotter = ProductionPlotter()
        self.waste_plotter = WastePlotter()
        
    def plot_accumulated_products(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot accumulated products over time"""
        self.production_plotter.plot_accumulated_products(processing_history, save_path)

    def plot_waste_mix(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot waste mix analysis"""
        self.waste_plotter.plot_waste_mix(processing_history, save_path)

    def plot_collection_efficiency(
        self,
        collection_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot collection efficiency metrics"""
        fig, axes = self.setup_figure(2, 1)
        
        # Plot system-wide efficiency
        self._plot_system_collection_efficiency(axes[0], collection_history)
        
        # Plot collection statistics
        self._plot_collection_statistics(axes[1], collection_history)
        
        self.save_figure(fig, save_path)

    def plot_treatment_metrics(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot treatment facility metrics"""
        fig, axes = self.setup_figure(2, 1)
        
        # Plot operational metrics
        self._plot_operational_metrics(axes[0], processing_history)
        
        # Plot resource utilization
        self._plot_resource_utilization(axes[1], processing_history)
        
        self.save_figure(fig, save_path)

    def plot_demand_metrics(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot demand satisfaction metrics"""
        fig, axes = self.setup_figure(2, 1)
        
        # Plot processing vs demand
        self._plot_aggregated_processing_vs_demand(axes[0], processing_history)
        
        # Plot system satisfaction
        self._plot_system_satisfaction(axes[1], processing_history)
        
        self.save_figure(fig, save_path)

    def _plot_system_collection_efficiency(
        self,
        ax: plt.Axes,
        collection_history: Dict[str, Any]
    ) -> None:
        """Plot system-wide collection efficiency"""
        timestamps = self.get_timestamps(collection_history)
        
        # Calculate average efficiency
        avg_efficiency = []
        for t_idx in range(len(timestamps)):
            efficiencies = [
                history["efficiency"][t_idx]
                for history in collection_history.values()
                if len(history["efficiency"]) > t_idx
            ]
            avg_efficiency.append(
                sum(efficiencies) / len(efficiencies) if efficiencies else 0
            )
        
        # Plot with moving average
        add_moving_average_plot(
            ax=ax,
            timestamps=timestamps,
            data=avg_efficiency,
            label="Efficiency",
            color="blue"
        )
        
        setup_axis_labels(
            ax,
            "System-wide Collection Efficiency",
            ylabel="Efficiency"
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    def _plot_collection_statistics(
        self,
        ax: plt.Axes,
        collection_history: Dict[str, Any]
    ) -> None:
        """Plot collection statistics summary"""
        ax.axis("off")
        
        # Calculate statistics for each collector
        stats_data = []
        for name, history in collection_history.items():
            efficiency = history["efficiency"]
            # Calculate end-of-simulation volume
            final_volume = sum(
                volumes[-1] if volumes else 0 
                for volumes in history["collected_volumes"].values()
            )
            # Calculate average volume across all timesteps
            avg_volume = np.mean([
                sum(vol[i] if len(vol) > i else 0 for vol in history["collected_volumes"].values())
                for i in range(len(history["timestamps"]))
            ])
            stats_data.append(
                [
                    name,
                    f"{sum(efficiency) / len(efficiency):.1f}%",
                    f"{final_volume:.1f}",
                    f"{avg_volume:.1f}",
                    f"{min(efficiency):.1f}%",
                    f"{max(efficiency):.1f}%",
                ]
            )

        # Sort by average efficiency
        stats_data.sort(key=lambda x: float(x[1][:-1]), reverse=True)

        # Create table
        table = ax.table(
            cellText=stats_data,
            colLabels=[
                "Collector",
                "Avg Efficiency",
                "Final Volume",
                "Avg Volume",
                "Min Efficiency",
                "Max Efficiency",
            ],
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)

        # Style header
        for j in range(6):
            table[(0, j)].set_facecolor("#E6E6E6")

        ax.set_title("Collection Performance Summary", pad=20)

    def _plot_operational_metrics(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any]
    ) -> None:
        """Plot operational metrics with moving averages"""
        timestamps = self.get_timestamps(processing_history)

        # Calculate metrics
        metrics = {
            "Conversion": [],
            "Energy": []
        }
        
        for t_idx in range(len(timestamps)):
            # Average conversion rate
            rates = [
                history["operational"]["conversion_rate"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["conversion_rate"]) > t_idx
            ]
            metrics["Conversion"].append(sum(rates) / len(rates) if rates else 0)

            # Average energy efficiency
            energy = [
                history["operational"]["energy_consumption"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["energy_consumption"]) > t_idx
            ]
            metrics["Energy"].append(sum(energy) / len(energy) if energy else 0)

        # Plot metrics using utility function
        colors = {
            "Conversion": "blue",
            "Energy": "green"
        }
        plot_multi_series(
            ax=ax,
            timestamps=timestamps,
            series_data=metrics,
            colors=colors,
            title="Operational Performance",
            ylabel="Rate"
        )

    def _plot_resource_utilization(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any]
    ) -> None:
        """Plot resource utilization metrics"""
        timestamps = self.get_timestamps(processing_history)

        # Calculate processing/storage ratios
        ratios = []
        for t_idx in range(len(timestamps)):
            timestep_ratios = []
            for history in processing_history.values():
                if (
                    len(history["processed"]["total"]) > t_idx
                    and len(history["storage"]["total"]) > t_idx
                ):
                    proc = history["processed"]["total"][t_idx]
                    stor = history["storage"]["total"][t_idx]
                    if stor > 0:
                        timestep_ratios.append(proc / stor)
            ratios.append(
                sum(timestep_ratios) / len(timestep_ratios) if timestep_ratios else 0
            )

        # Plot using utility function
        add_moving_average_plot(
            ax=ax,
            timestamps=timestamps,
            data=ratios,
            label="Utilization",
            color="blue"
        )

        setup_axis_labels(
            ax,
            "Resource Utilization",
            ylabel="Processing/Storage Ratio"
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    def _plot_aggregated_processing_vs_demand(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any]
    ) -> None:
        """Plot processing vs demand with moving average"""
        timestamps = self.get_timestamps(processing_history)

        # Calculate metrics
        metrics = {
            "Processing": [],
            "Demand": []
        }
        
        for t_idx in range(len(timestamps)):
            # Sum processing
            proc_sum = sum(
                history["processed"]["total"][t_idx]
                for history in processing_history.values()
                if len(history["processed"]["total"]) > t_idx
            )
            metrics["Processing"].append(proc_sum)

            # Sum demand
            demand_sum = sum(
                history["operational"]["demand"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["demand"]) > t_idx
            )
            metrics["Demand"].append(demand_sum)

        # Plot metrics using utility function
        colors = {
            "Processing": "blue",
            "Demand": "red"
        }
        plot_multi_series(
            ax=ax,
            timestamps=timestamps,
            series_data=metrics,
            colors=colors,
            title="System-wide Processing vs. Demand",
            ylabel=VOLUME_LABEL
        )

    def _plot_system_satisfaction(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any]
    ) -> None:
        """Plot system-wide demand satisfaction rate"""
        timestamps = self.get_timestamps(processing_history)

        # Calculate satisfaction rate
        satisfaction_rate = []
        for t_idx in range(len(timestamps)):
            total_processed = sum(
                history["processed"]["total"][t_idx]
                for history in processing_history.values()
                if len(history["processed"]["total"]) > t_idx
            )
            total_demand = sum(
                history["operational"]["demand"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["demand"]) > t_idx
            )
            rate = (total_processed / total_demand * 100) if total_demand > 0 else 0
            satisfaction_rate.append(rate)

        # Plot using utility function
        add_moving_average_plot(
            ax=ax,
            timestamps=timestamps,
            data=satisfaction_rate,
            label="Satisfaction",
            color="blue"
        )

        setup_axis_labels(
            ax,
            "System-wide Demand Satisfaction",
            ylabel="Satisfaction Rate (%)"
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
