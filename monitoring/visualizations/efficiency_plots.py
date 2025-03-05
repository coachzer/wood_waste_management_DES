from typing import Dict, Any
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from ..visualizations.plot_utils import (
    VOLUME_LABEL,
    DEFAULT_FIGURE_SIZE,
    GRID_ALPHA,
    add_year_demarcations,
    setup_axis_labels,
    save_plot,
)


class EfficiencyPlotter:
    """Handles plotting of efficiency-related metrics"""

    @staticmethod
    def plot_collection_efficiency(
        collection_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot aggregated collection efficiency metrics"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # System-wide efficiency
        ax1 = fig.add_subplot(gs[0])
        EfficiencyPlotter._plot_system_collection_efficiency(ax1, collection_history)

        # Regional comparison
        ax2 = fig.add_subplot(gs[1])
        EfficiencyPlotter._plot_collection_statistics(ax2, collection_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def plot_treatment_metrics(
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot aggregated treatment facility metrics"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Operational efficiency metrics
        ax1 = fig.add_subplot(gs[0])
        EfficiencyPlotter._plot_operational_metrics(ax1, processing_history)

        # Resource utilization
        ax2 = fig.add_subplot(gs[1])
        EfficiencyPlotter._plot_resource_utilization(ax2, processing_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_system_collection_efficiency(
        ax: plt.Axes, collection_history: Dict[str, Any]
    ) -> None:
        """Plot system-wide collection efficiency with moving average"""
        timestamps = next(iter(collection_history.values()))["timestamps"]
        window = 5

        # Calculate average efficiency across collectors
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

        # Plot raw data and moving average
        ax.plot(
            timestamps,
            avg_efficiency,
            alpha=0.2,
            color="blue",
            label="Efficiency (Raw)",
        )

        # Calculate and plot moving average
        ma = [
            sum(
                avg_efficiency[
                    max(0, i - window) : min(len(avg_efficiency), i + window + 1)
                ]
            )
            / (min(len(avg_efficiency), i + window + 1) - max(0, i - window))
            for i in range(len(avg_efficiency))
        ]
        ax.plot(timestamps, ma, color="blue", linewidth=2, label="Efficiency (MA)")

        setup_axis_labels(
            ax,
            "System-wide Collection Efficiency",
            ylabel="Efficiency",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_collection_statistics(
        ax: plt.Axes, collection_history: Dict[str, Any]
    ) -> None:
        """Plot collection statistics summary"""
        ax.axis("off")

        # Calculate statistics for each collector
        stats_data = []
        for name, history in collection_history.items():
            efficiency = history["efficiency"]
            total_collections = sum(
                sum(volumes) for volumes in history["collected_volumes"].values()
            )
            stats_data.append(
                [
                    name,
                    f"{sum(efficiency) / len(efficiency):.1f}%",
                    f"{total_collections:.1f}",
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
                "Total Volume",
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
        for j in range(5):
            table[(0, j)].set_facecolor("#E6E6E6")

        ax.set_title("Collection Performance Summary", pad=20)

    @staticmethod
    def _plot_operational_metrics(
        ax: plt.Axes, processing_history: Dict[str, Any]
    ) -> None:
        """Plot aggregated operational metrics with moving averages"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Calculate average metrics
        conversion_rate = []
        energy_efficiency = []

        for t_idx in range(len(timestamps)):
            # Average conversion rate
            rates = [
                history["operational"]["conversion_rate"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["conversion_rate"]) > t_idx
            ]
            conversion_rate.append(sum(rates) / len(rates) if rates else 0)

            # Average energy efficiency
            energy = [
                history["operational"]["energy_consumption"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["energy_consumption"]) > t_idx
            ]
            energy_efficiency.append(sum(energy) / len(energy) if energy else 0)

        # Plot raw data
        ax.plot(
            timestamps,
            conversion_rate,
            alpha=0.2,
            color="blue",
            label="Conversion (Raw)",
        )
        ax.plot(
            timestamps,
            energy_efficiency,
            alpha=0.2,
            color="green",
            label="Energy (Raw)",
        )

        # Calculate and plot moving averages
        def calc_ma(data):
            return [
                sum(data[max(0, i - window) : min(len(data), i + window + 1)])
                / (min(len(data), i + window + 1) - max(0, i - window))
                for i in range(len(data))
            ]

        conv_ma = calc_ma(conversion_rate)
        energy_ma = calc_ma(energy_efficiency)

        ax.plot(timestamps, conv_ma, color="blue", linewidth=2, label="Conversion (MA)")
        ax.plot(timestamps, energy_ma, color="green", linewidth=2, label="Energy (MA)")

        setup_axis_labels(
            ax,
            "Operational Performance",
            ylabel="Rate",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_resource_utilization(
        ax: plt.Axes, processing_history: Dict[str, Any]
    ) -> None:
        """Plot aggregated resource utilization metrics"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Calculate average processing/storage ratio
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

        # Plot raw data
        ax.plot(timestamps, ratios, alpha=0.2, color="blue", label="Utilization (Raw)")

        # Calculate and plot moving average
        ma = [
            sum(ratios[max(0, i - window) : min(len(ratios), i + window + 1)])
            / (min(len(ratios), i + window + 1) - max(0, i - window))
            for i in range(len(ratios))
        ]
        ax.plot(timestamps, ma, color="blue", linewidth=2, label="Utilization (MA)")

        setup_axis_labels(ax, "Resource Utilization", ylabel="Processing/Storage Ratio")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def plot_demand_metrics(
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot aggregated demand satisfaction metrics"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Average processing vs. demand
        ax1 = fig.add_subplot(gs[0])
        EfficiencyPlotter._plot_aggregated_processing_vs_demand(ax1, processing_history)

        # System-wide demand satisfaction
        ax2 = fig.add_subplot(gs[1])
        EfficiencyPlotter._plot_system_satisfaction(ax2, processing_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def plot_product_mix(
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot aggregated product mix analysis"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Aggregated product mix
        ax1 = fig.add_subplot(gs[0])
        EfficiencyPlotter._plot_aggregated_product_mix(ax1, processing_history)

        # Summary statistics
        ax2 = fig.add_subplot(gs[1])
        EfficiencyPlotter._plot_product_summary(ax2, processing_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_aggregated_processing_vs_demand(
        ax: plt.Axes, processing_history: Dict[str, Any]
    ) -> None:
        """Plot aggregated processing vs. demand with moving average"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Calculate total processing and demand
        total_processed = []
        total_demand = []

        for t_idx in range(len(timestamps)):
            # Sum processing across all facilities
            proc_sum = sum(
                history["processed"]["total"][t_idx]
                for history in processing_history.values()
                if len(history["processed"]["total"]) > t_idx
            )
            total_processed.append(proc_sum)

            # Sum demand across all facilities
            demand_sum = sum(
                history["operational"]["demand"][t_idx]
                for history in processing_history.values()
                if len(history["operational"]["demand"]) > t_idx
            )
            total_demand.append(demand_sum)

        # Plot raw data (transparent)
        ax.plot(
            timestamps,
            total_processed,
            alpha=0.2,
            color="blue",
            label="Processing (Raw)",
        )
        ax.plot(
            timestamps,
            total_demand,
            alpha=0.2,
            color="red",
            label="Demand (Raw)",
        )

        # Calculate and plot moving averages
        def calc_ma(data):
            return [
                sum(data[max(0, i - window) : min(len(data), i + window + 1)])
                / (min(len(data), i + window + 1) - max(0, i - window))
                for i in range(len(data))
            ]

        proc_ma = calc_ma(total_processed)
        demand_ma = calc_ma(total_demand)

        ax.plot(timestamps, proc_ma, color="blue", linewidth=2, label="Processing (MA)")
        ax.plot(timestamps, demand_ma, color="red", linewidth=2, label="Demand (MA)")

        setup_axis_labels(ax, "System-wide Processing vs. Demand", ylabel=VOLUME_LABEL)
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_system_satisfaction(
        ax: plt.Axes, processing_history: Dict[str, Any]
    ) -> None:
        """Plot system-wide demand satisfaction rate"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Calculate overall satisfaction rate
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

        # Plot raw data
        ax.plot(
            timestamps,
            satisfaction_rate,
            alpha=0.2,
            color="blue",
            label="Satisfaction (Raw)",
        )

        # Calculate and plot moving average
        ma = [
            sum(
                satisfaction_rate[
                    max(0, i - window) : min(len(satisfaction_rate), i + window + 1)
                ]
            )
            / (min(len(satisfaction_rate), i + window + 1) - max(0, i - window))
            for i in range(len(satisfaction_rate))
        ]
        ax.plot(timestamps, ma, color="blue", linewidth=2, label="Satisfaction (MA)")

        setup_axis_labels(
            ax, "System-wide Demand Satisfaction", ylabel="Satisfaction Rate (%)"
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_aggregated_product_mix(
        ax: plt.Axes, processing_history: Dict[str, Any]
    ) -> None:
        """Plot aggregated product mix across all facilities"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Aggregate by waste type
        waste_types = set()
        for history in processing_history.values():
            waste_types.update(history["processed"]["by_type"].keys())

        # Calculate totals for each waste type
        waste_totals = {}
        for waste_type in waste_types:
            totals = []
            for t_idx in range(len(timestamps)):
                total = sum(
                    history["processed"]["by_type"][waste_type][t_idx]
                    for history in processing_history.values()
                    if waste_type in history["processed"]["by_type"]
                    and len(history["processed"]["by_type"][waste_type]) > t_idx
                )
                totals.append(total)
            waste_totals[waste_type] = totals

        # Plot with moving averages
        colors = plt.cm.tab10(np.linspace(0, 1, len(waste_types)))
        for (waste_type, totals), color in zip(waste_totals.items(), colors):
            # Raw data
            ax.plot(
                timestamps,
                totals,
                alpha=0.2,
                color=color,
                label=f"{waste_type.value} (Raw)",
            )

            # Moving average
            ma = [
                sum(totals[max(0, i - window) : min(len(totals), i + window + 1)])
                / (min(len(totals), i + window + 1) - max(0, i - window))
                for i in range(len(totals))
            ]
            ax.plot(
                timestamps,
                ma,
                color=color,
                linewidth=2,
                label=f"{waste_type.value} (MA)",
            )

        setup_axis_labels(ax, "Product Mix Over Time", ylabel=VOLUME_LABEL)
        ax.legend(bbox_to_anchor=(1.05, 1))
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_product_summary(ax: plt.Axes, processing_history: Dict[str, Any]) -> None:
        """Plot summary of product mix distribution"""
        # Create summary table
        ax.axis("off")
        waste_types = set()
        for history in processing_history.values():
            waste_types.update(history["processed"]["by_type"].keys())

        summary_data = []
        for waste_type in waste_types:
            total_volume = sum(
                sum(history["processed"]["by_type"][waste_type])
                for history in processing_history.values()
                if waste_type in history["processed"]["by_type"]
            )
            summary_data.append([waste_type.value, f"{total_volume:.1f}"])

        # Sort by volume
        summary_data.sort(key=lambda x: float(x[1]), reverse=True)

        # Create table
        table = ax.table(
            cellText=summary_data,
            colLabels=["Product Type", "Total Volume"],
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)

        # Style header
        for j in range(2):
            table[(0, j)].set_facecolor("#E6E6E6")

        ax.set_title("Product Distribution Summary", pad=20)
