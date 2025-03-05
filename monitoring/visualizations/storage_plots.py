from typing import Dict, Any
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from ..visualizations.plot_utils import (
    STORAGE_UTIL_LABEL,
    DEFAULT_FIGURE_SIZE,
    GRID_ALPHA,
    LEGEND_FONTSIZE,
    create_grouped_plot,
    setup_axis_labels,
    save_plot,
)


class StoragePlotter:
    """Handles plotting of storage-related metrics and analysis"""

    @staticmethod
    def plot_storage_levels(
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot aggregated storage levels across the system"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Aggregated storage by facility type
        ax1 = fig.add_subplot(gs[0])
        StoragePlotter._plot_aggregated_storage_by_type(
            ax1, generation_history, processing_history, collection_history
        )

        # System-wide storage trend
        ax2 = fig.add_subplot(gs[1])
        StoragePlotter._plot_system_storage_trend(
            ax2, generation_history, processing_history, collection_history
        )

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def plot_detailed_storage_analysis(
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Create a simplified summary of storage patterns"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Average utilization by type with error bars
        ax1 = fig.add_subplot(gs[0])
        StoragePlotter._plot_storage_statistics(
            ax1, generation_history, processing_history
        )

        # Peak storage periods analysis
        ax2 = fig.add_subplot(gs[1])
        StoragePlotter._plot_peak_storage_analysis(
            ax2, generation_history, processing_history
        )

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_aggregated_storage_by_type(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        collection_history: Dict[str, Any],
    ) -> None:
        """Plot aggregated storage levels by facility type"""
        timestamps = next(iter(generation_history.values()))["timestamps"]

        # Calculate average storage utilization for each type
        generator_util = []
        treatment_util = []
        collector_util = []

        for t_idx in range(len(timestamps)):
            # Generator average
            gen_utils = [
                history["storage_utilization"][t_idx]
                for history in generation_history.values()
                if len(history["storage_utilization"]) > t_idx
            ]
            generator_util.append(sum(gen_utils) / len(gen_utils) if gen_utils else 0)

            # Treatment average
            treat_utils = [
                history["storage"]["utilization"][t_idx]
                for history in processing_history.values()
                if len(history["storage"]["utilization"]) > t_idx
            ]
            treatment_util.append(
                sum(treat_utils) / len(treat_utils) if treat_utils else 0
            )

            # Collector average
            col_totals = []
            for history in collection_history.values():
                if t_idx < len(history["timestamps"]):
                    total = sum(
                        volumes[t_idx]
                        for volumes in history["collected_volumes"].values()
                        if len(volumes) > t_idx
                    )
                    if total > 0:
                        col_totals.append(total)

            collector_util.append(
                sum(col_totals) / len(col_totals) if col_totals else 0
            )

        # Plot aggregated trends
        ax.plot(
            timestamps,
            generator_util,
            label="Generators",
            marker="o",
            markersize=4,
            markevery=5,
        )
        ax.plot(
            timestamps,
            treatment_util,
            label="Treatment",
            marker="s",
            markersize=4,
            markevery=5,
        )
        ax.plot(
            timestamps,
            collector_util,
            label="Collectors",
            marker="^",
            markersize=4,
            markevery=5,
        )

        setup_axis_labels(
            ax,
            "Average Storage Utilization by Facility Type",
            ylabel=STORAGE_UTIL_LABEL,
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
        ax.set_ylim(0, 100)

    @staticmethod
    def _plot_system_storage_trend(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        collection_history: Dict[str, Any],
    ) -> None:
        """Plot overall system storage trend"""
        timestamps = next(iter(generation_history.values()))["timestamps"]

        # Calculate total system storage
        total_storage = []
        for t_idx in range(len(timestamps)):
            timestep_total = 0

            # Add generator storage
            for history in generation_history.values():
                if len(history["storage_utilization"]) > t_idx:
                    timestep_total += history["storage_utilization"][t_idx]

            # Add treatment storage
            for history in processing_history.values():
                if len(history["storage"]["utilization"]) > t_idx:
                    timestep_total += history["storage"]["utilization"][t_idx]

            # Add collector storage
            for history in collection_history.values():
                if t_idx < len(history["timestamps"]):
                    total = sum(
                        volumes[t_idx]
                        for volumes in history["collected_volumes"].values()
                        if len(volumes) > t_idx
                    )
                    if total > 0:
                        timestep_total += total

            total_storage.append(timestep_total)

        # Plot trend with moving average
        ax.plot(timestamps, total_storage, alpha=0.3, color="gray", label="Raw")
        window = 5
        moving_avg = [
            sum(
                total_storage[
                    max(0, i - window) : min(len(total_storage), i + window + 1)
                ]
            )
            / (min(len(total_storage), i + window + 1) - max(0, i - window))
            for i in range(len(total_storage))
        ]
        ax.plot(timestamps, moving_avg, linewidth=2, label="Moving Average")

        setup_axis_labels(
            ax,
            "System-wide Storage Trend",
            ylabel="Total Storage Level",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_storage_statistics(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot storage statistics with error bars"""
        # Calculate statistics for generators and treatment facilities
        facility_types = ["Generators", "Treatment"]
        means = []
        errors = []

        # Generator statistics
        gen_data = []
        for history in generation_history.values():
            if history["storage_utilization"]:
                gen_data.extend(history["storage_utilization"])
        if gen_data:
            means.append(sum(gen_data) / len(gen_data))
            errors.append(
                (max(gen_data) - min(gen_data)) / 2
            )  # Use range as error bars
        else:
            means.append(0)
            errors.append(0)

        # Treatment facility statistics
        treat_data = []
        for history in processing_history.values():
            if "storage" in history and "utilization" in history["storage"]:
                treat_data.extend(history["storage"]["utilization"])
        if treat_data:
            means.append(sum(treat_data) / len(treat_data))
            errors.append((max(treat_data) - min(treat_data)) / 2)
        else:
            means.append(0)
            errors.append(0)

        # Create bar plot with error bars
        x_pos = range(len(facility_types))
        bars = ax.bar(x_pos, means, yerr=errors, capsize=5)

        # Customize plot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(facility_types)
        setup_axis_labels(
            ax,
            "Average Storage Utilization by Facility Type",
            ylabel=STORAGE_UTIL_LABEL,
        )
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

        # Add value labels
        for bar, mean, error in zip(bars, means, errors):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + error,
                f"{mean:.1f}%",
                ha="center",
                va="bottom",
            )

    @staticmethod
    def _plot_peak_storage_analysis(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot peak storage periods analysis"""
        timestamps = next(iter(generation_history.values()))["timestamps"]
        threshold_percentile = 90  # Define peak as top 10% of storage levels

        # Calculate total system storage at each timestamp
        total_storage = []
        for t_idx in range(len(timestamps)):
            timestep_total = 0

            # Add generator and treatment facility storage
            for history in generation_history.values():
                if len(history["storage_utilization"]) > t_idx:
                    timestep_total += history["storage_utilization"][t_idx]

            for history in processing_history.values():
                if len(history["storage"]["utilization"]) > t_idx:
                    timestep_total += history["storage"]["utilization"][t_idx]

            total_storage.append(timestep_total)

        # Calculate threshold for peak periods
        peak_threshold = sorted(total_storage)[
            int(len(total_storage) * threshold_percentile / 100)
        ]

        # Create the plot
        ax.plot(
            timestamps, total_storage, label="Total Storage", color="blue", alpha=0.6
        )
        ax.axhline(
            y=peak_threshold,
            color="red",
            linestyle="--",
            label=f"{threshold_percentile}th Percentile",
        )

        # Highlight peak periods
        peak_periods = [level >= peak_threshold for level in total_storage]
        ax.fill_between(
            timestamps,
            total_storage,
            peak_threshold,
            where=[level >= peak_threshold for level in total_storage],
            color="red",
            alpha=0.2,
            label="Peak Periods",
        )

        setup_axis_labels(
            ax,
            "Peak Storage Analysis",
            ylabel="Total Storage Level",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
