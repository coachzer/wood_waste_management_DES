from typing import Dict, Any
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from ..visualizations.plot_utils import (
    VOLUME_LABEL,
    DEFAULT_FIGURE_SIZE,
    GRID_ALPHA,
    setup_axis_labels,
    save_plot,
)


import numpy as np
import seaborn as sns


class SystemPlotter:
    """Handles plotting of system-wide performance metrics"""

    @staticmethod
    def plot_entity_heatmaps(
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Create heatmaps for generators, collectors, and processors metrics"""
        fig = plt.figure(figsize=(20, 15))
        gs = GridSpec(3, 2, figure=fig)

        # Generator heatmaps
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        SystemPlotter._create_generator_heatmaps(ax1, ax2, generation_history)

        # Collector heatmaps
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])
        SystemPlotter._create_collector_heatmaps(ax3, ax4, collection_history)

        # Processor heatmaps
        ax5 = fig.add_subplot(gs[2, 0])
        ax6 = fig.add_subplot(gs[2, 1])
        SystemPlotter._create_processor_heatmaps(ax5, ax6, processing_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _create_generator_heatmaps(
        ax1: plt.Axes,
        ax2: plt.Axes,
        generation_history: Dict[str, Any],
    ) -> None:
        """Create heatmaps for generator metrics"""
        entities = list(generation_history.keys())
        timestamps = generation_history[entities[0]]["timestamps"]

        # Storage utilization heatmap
        storage_data = np.array(
            [generation_history[entity]["storage_utilization"] for entity in entities]
        )
        sns.heatmap(
            storage_data, ax=ax1, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(
            ax1, "Generator Storage Utilization", xlabel="Time", ylabel="Generator"
        )

        # Total generation heatmap
        gen_data = np.array(
            [
                [
                    sum(
                        generation_history[entity]["total_generated"][wtype][t]
                        for wtype in generation_history[entity]["total_generated"]
                    )
                    for t in range(len(timestamps))
                ]
                for entity in entities
            ]
        )
        sns.heatmap(
            gen_data, ax=ax2, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(
            ax2, "Generator Total Generation", xlabel="Time", ylabel="Generator"
        )

    @staticmethod
    def _create_collector_heatmaps(
        ax1: plt.Axes,
        ax2: plt.Axes,
        collection_history: Dict[str, Any],
    ) -> None:
        """Create heatmaps for collector metrics"""
        entities = list(collection_history.keys())
        timestamps = collection_history[entities[0]]["timestamps"]

        # Collection volumes heatmap
        vol_data = np.array(
            [
                [
                    sum(
                        collection_history[entity]["collected_volumes"][wtype][t]
                        for wtype in collection_history[entity]["collected_volumes"]
                    )
                    for t in range(len(timestamps))
                ]
                for entity in entities
            ]
        )
        sns.heatmap(
            vol_data, ax=ax1, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(ax1, "Collector Volumes", xlabel="Time", ylabel="Collector")

        # Efficiency heatmap
        eff_data = np.array(
            [collection_history[entity]["efficiency"] for entity in entities]
        )
        sns.heatmap(
            eff_data, ax=ax2, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(
            ax2, "Collector Efficiency", xlabel="Time", ylabel="Collector"
        )

    @staticmethod
    def _create_processor_heatmaps(
        ax1: plt.Axes,
        ax2: plt.Axes,
        processing_history: Dict[str, Any],
    ) -> None:
        """Create heatmaps for processor metrics"""
        entities = list(processing_history.keys())
        timestamps = processing_history[entities[0]]["timestamps"]

        # Storage utilization heatmap
        storage_data = np.array(
            [
                processing_history[entity]["storage"]["utilization"]
                for entity in entities
            ]
        )
        sns.heatmap(
            storage_data, ax=ax1, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(
            ax1, "Processor Storage Utilization", xlabel="Time", ylabel="Processor"
        )

        # Processing volumes heatmap
        proc_data = np.array(
            [processing_history[entity]["processed"]["total"] for entity in entities]
        )
        sns.heatmap(
            proc_data, ax=ax2, cmap="YlOrRd", xticklabels=50, yticklabels=entities
        )
        setup_axis_labels(ax2, "Processor Volumes", xlabel="Time", ylabel="Processor")

    @staticmethod
    def plot_product_mix(
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Create a pie chart showing the distribution of processed waste types"""
        fig, ax = plt.subplots(figsize=(12, 8))

        # Calculate total processed volumes by type
        total_by_type = {}
        for facility in processing_history.values():
            for waste_type, volumes in facility["processed"]["by_type"].items():
                if volumes:  # Only include if there are values
                    total = volumes[-1]  # Get the final value
                    if waste_type in total_by_type:
                        total_by_type[waste_type] += total
                    else:
                        total_by_type[waste_type] = total

        # Create pie chart
        labels = [wtype.value for wtype in total_by_type.keys()]
        values = list(total_by_type.values())

        # Only include non-zero values
        non_zero_mask = np.array(values) > 0
        labels = [label for label, include in zip(labels, non_zero_mask) if include]
        values = [value for value, include in zip(values, non_zero_mask) if include]

        if values:  # Only create pie chart if we have values
            patches, texts, autotexts = ax.pie(
                values, labels=labels, autopct="%1.1f%%", startangle=90
            )
            plt.setp(autotexts, fontsize=8, weight="bold")
            plt.setp(texts, fontsize=10)

            setup_axis_labels(ax, "Product Mix Distribution")

            plt.tight_layout()
            save_plot(fig, save_path)

    @staticmethod
    def plot_system_performance(
        efficiency_metrics: Dict[str, float],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot overall system performance metrics"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Overall efficiency metrics
        ax1 = fig.add_subplot(gs[0])
        SystemPlotter._plot_overall_efficiency(ax1, efficiency_metrics)

        # System performance over time
        ax2 = fig.add_subplot(gs[1])
        SystemPlotter._plot_performance_trends(
            ax2, collection_history, processing_history
        )

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_overall_efficiency(
        ax: plt.Axes,
        efficiency_metrics: Dict[str, float],
    ) -> None:
        """Plot overall system efficiency metrics with error bars"""
        metrics = ["Collection", "Processing", "Overall"]
        values = [
            efficiency_metrics["collection_rate"],
            efficiency_metrics["processing_rate"],
            efficiency_metrics["overall_efficiency"],
        ]

        # Create bar plot
        x_pos = range(len(metrics))
        bars = ax.bar(x_pos, values)

        # Customize plot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(metrics)
        setup_axis_labels(
            ax,
            "System Efficiency Overview",
            ylabel="Efficiency (%)",
        )
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

        # Add value labels
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{val:.1f}%",
                ha="center",
                va="bottom",
            )

    @staticmethod
    def _plot_performance_trends(
        ax: plt.Axes,
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot aggregated performance trends over time"""
        timestamps = next(iter(collection_history.values()))["timestamps"]
        window = 5  # Moving average window size

        # Calculate aggregated metrics
        collection_rate = []
        processing_rate = []

        for t_idx in range(len(timestamps)):
            # Total collection at time t
            total_collected = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["collected_volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in collection_history.values()
            )
            collection_rate.append(total_collected)

            # Total processing at time t
            total_processed = sum(
                (
                    history["processed"]["total"][t_idx]
                    if len(history["processed"]["total"]) > t_idx
                    else 0
                )
                for history in processing_history.values()
            )
            processing_rate.append(total_processed)

        # Calculate moving averages
        def moving_average(data):
            return [
                sum(data[max(0, i - window) : min(len(data), i + window + 1)])
                / (min(len(data), i + window + 1) - max(0, i - window))
                for i in range(len(data))
            ]

        collection_ma = moving_average(collection_rate)
        processing_ma = moving_average(processing_rate)

        # Plot both raw data (transparent) and moving averages
        ax.plot(
            timestamps,
            collection_rate,
            alpha=0.2,
            color="blue",
            label="Collection (Raw)",
        )
        ax.plot(
            timestamps,
            processing_rate,
            alpha=0.2,
            color="green",
            label="Processing (Raw)",
        )
        ax.plot(
            timestamps,
            collection_ma,
            color="blue",
            linewidth=2,
            label="Collection (MA)",
        )
        ax.plot(
            timestamps,
            processing_ma,
            color="green",
            linewidth=2,
            label="Processing (MA)",
        )

        setup_axis_labels(
            ax,
            "System Performance Over Time",
            ylabel=VOLUME_LABEL,
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def plot_system_balance(
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot simplified system balance analysis"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Material flow balance
        ax1 = fig.add_subplot(gs[0])
        SystemPlotter._plot_material_flow(
            ax1, generation_history, collection_history, processing_history
        )

        # Processing efficiency
        ax2 = fig.add_subplot(gs[1])
        SystemPlotter._plot_aggregated_processing(ax2, processing_history)

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_material_flow(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot aggregated material flow balance"""
        timestamps = next(iter(generation_history.values()))["timestamps"]
        window = 5

        # Calculate system-wide totals
        totals = {"Generated": [], "Collected": [], "Processed": []}

        for t_idx in range(len(timestamps)):
            # Total generation
            gen_total = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in generation_history.values()
            )
            totals["Generated"].append(gen_total)

            # Total collection
            col_total = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["collected_volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in collection_history.values()
            )
            totals["Collected"].append(col_total)

            # Total processing
            proc_total = sum(
                (
                    history["processed"]["total"][t_idx]
                    if len(history["processed"]["total"]) > t_idx
                    else 0
                )
                for history in processing_history.values()
            )
            totals["Processed"].append(proc_total)

        # Plot with moving averages
        colors = {"Generated": "blue", "Collected": "green", "Processed": "red"}
        for key, data in totals.items():
            # Raw data (transparent)
            ax.plot(
                timestamps, data, alpha=0.2, color=colors[key], label=f"{key} (Raw)"
            )

            # Moving average
            ma = [
                sum(data[max(0, i - window) : min(len(data), i + window + 1)])
                / (min(len(data), i + window + 1) - max(0, i - window))
                for i in range(len(data))
            ]
            ax.plot(timestamps, ma, color=colors[key], linewidth=2, label=f"{key} (MA)")

        setup_axis_labels(
            ax,
            "Material Flow Balance",
            ylabel=VOLUME_LABEL,
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_aggregated_processing(
        ax: plt.Axes,
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot aggregated processing efficiency"""
        timestamps = next(iter(processing_history.values()))["timestamps"]
        window = 5

        # Calculate average efficiency metrics
        efficiency = []
        satisfaction = []

        for t_idx in range(len(timestamps)):
            # Average efficiency at time t
            eff_values = []
            sat_values = []

            for history in processing_history.values():
                if len(history["operational"]["conversion_rate"]) > t_idx:
                    eff_values.append(history["operational"]["conversion_rate"][t_idx])
                if len(history["operational"]["demand_satisfaction"]) > t_idx:
                    sat_values.append(
                        history["operational"]["demand_satisfaction"][t_idx] * 100
                    )

            efficiency.append(sum(eff_values) / len(eff_values) if eff_values else 0)
            satisfaction.append(sum(sat_values) / len(sat_values) if sat_values else 0)

        # Plot with moving averages
        ax.plot(
            timestamps, efficiency, alpha=0.2, color="blue", label="Efficiency (Raw)"
        )
        ax.plot(
            timestamps,
            satisfaction,
            alpha=0.2,
            color="green",
            label="Satisfaction (Raw)",
        )

        # Calculate and plot moving averages
        eff_ma = [
            sum(efficiency[max(0, i - window) : min(len(efficiency), i + window + 1)])
            / (min(len(efficiency), i + window + 1) - max(0, i - window))
            for i in range(len(efficiency))
        ]
        sat_ma = [
            sum(
                satisfaction[
                    max(0, i - window) : min(len(satisfaction), i + window + 1)
                ]
            )
            / (min(len(satisfaction), i + window + 1) - max(0, i - window))
            for i in range(len(satisfaction))
        ]

        ax.plot(timestamps, eff_ma, color="blue", linewidth=2, label="Efficiency (MA)")
        ax.plot(
            timestamps, sat_ma, color="green", linewidth=2, label="Satisfaction (MA)"
        )

        setup_axis_labels(
            ax,
            "Processing Performance",
            ylabel="Percentage (%)",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def plot_cumulative_analysis(
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot cumulative system performance analysis"""
        fig = plt.figure(figsize=DEFAULT_FIGURE_SIZE)
        gs = GridSpec(2, 1, figure=fig)

        # Cumulative totals
        ax1 = fig.add_subplot(gs[0])
        SystemPlotter._plot_cumulative_totals(
            ax1, generation_history, collection_history, processing_history
        )

        # Cumulative efficiency
        ax2 = fig.add_subplot(gs[1])
        SystemPlotter._plot_cumulative_efficiency(
            ax2, collection_history, processing_history
        )

        plt.tight_layout()
        save_plot(fig, save_path)

    @staticmethod
    def _plot_cumulative_totals(
        ax: plt.Axes,
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot cumulative system totals"""
        timestamps = next(iter(generation_history.values()))["timestamps"]

        # Calculate cumulative totals
        generated = []
        collected = []
        processed = []
        running_gen = 0
        running_col = 0
        running_proc = 0

        for t_idx in range(len(timestamps)):
            # Add generation
            gen_total = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in generation_history.values()
            )
            running_gen += gen_total
            generated.append(running_gen)

            # Add collection
            col_total = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["collected_volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in collection_history.values()
            )
            running_col += col_total
            collected.append(running_col)

            # Add processing
            proc_total = sum(
                (
                    history["processed"]["total"][t_idx]
                    if len(history["processed"]["total"]) > t_idx
                    else 0
                )
                for history in processing_history.values()
            )
            running_proc += proc_total
            processed.append(running_proc)

        # Plot cumulative trends
        ax.plot(timestamps, generated, label="Generated", linewidth=2)
        ax.plot(timestamps, collected, label="Collected", linewidth=2)
        ax.plot(timestamps, processed, label="Processed", linewidth=2)

        setup_axis_labels(
            ax,
            "Cumulative System Performance",
            ylabel=VOLUME_LABEL,
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    @staticmethod
    def _plot_cumulative_efficiency(
        ax: plt.Axes,
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> None:
        """Plot cumulative efficiency metrics"""
        timestamps = next(iter(collection_history.values()))["timestamps"]
        window = 5  # Moving average window for smoothing

        # Calculate cumulative efficiencies
        collection_eff = []
        processing_eff = []
        total_collected = 0
        total_processed = 0

        for t_idx in range(len(timestamps)):
            # Collection metrics
            time_collected = sum(
                sum(
                    volumes[t_idx]
                    for volumes in history["collected_volumes"].values()
                    if len(volumes) > t_idx
                )
                for history in collection_history.values()
            )
            total_collected += time_collected

            # Processing metrics
            time_processed = sum(
                (
                    history["processed"]["total"][t_idx]
                    if len(history["processed"]["total"]) > t_idx
                    else 0
                )
                for history in processing_history.values()
            )
            total_processed += time_processed

            # Calculate efficiencies
            collection_eff.append(total_collected)
            if total_collected > 0:
                processing_eff.append((total_processed / total_collected) * 100)
            else:
                processing_eff.append(0)

        # Plot raw data with light alpha
        ax.plot(
            timestamps,
            collection_eff,
            alpha=0.2,
            color="blue",
            label="Collection Volume",
        )
        ax.plot(
            timestamps,
            processing_eff,
            alpha=0.2,
            color="green",
            label="Processing Efficiency",
        )

        # Calculate and plot moving averages
        def moving_average(data):
            return [
                sum(data[max(0, i - window) : min(len(data), i + window + 1)])
                / (min(len(data), i + window + 1) - max(0, i - window))
                for i in range(len(data))
            ]

        col_ma = moving_average(collection_eff)
        proc_ma = moving_average(processing_eff)

        ax.plot(timestamps, col_ma, color="blue", linewidth=2, label="Collection (MA)")
        ax.plot(
            timestamps, proc_ma, color="green", linewidth=2, label="Processing (MA)"
        )

        setup_axis_labels(
            ax,
            "Cumulative Processing Efficiency",
            ylabel="Value",
        )
        ax.legend()
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
