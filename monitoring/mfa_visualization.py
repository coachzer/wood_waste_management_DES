import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List


def create_material_flow_analysis(
    generation_history: Dict,
    collection_history: Dict,
    processing_history: Dict,
    save_path: str = "plots/material_flow_analysis.png",
):
    """
    Create a Sankey-like visualization of material flows through the waste management system.
    Shows flows between generators, collectors, and treatment facilities.
    """
    plt.figure(figsize=(15, 10))

    # Calculate final volumes for each stage
    generator_volumes = {}
    for generator, history in generation_history.items():
        generator_volumes[generator] = sum(
            volumes[-1] if volumes else 0
            for volumes in history["total_generated"].values()
        )

    collector_volumes = {}
    for collector, history in collection_history.items():
        collector_volumes[collector] = sum(
            volumes[-1] if volumes else 0
            for volumes in history["collected_volumes"].values()
        )

    treatment_volumes = {}
    for treatment, history in processing_history.items():
        treatment_volumes[treatment] = (
            history["processed"]["total"][-1] if history["processed"]["total"] else 0
        )

    # Set up positions for nodes
    num_generators = len(generator_volumes)
    num_collectors = len(collector_volumes)
    num_treatments = len(treatment_volumes)

    y_gen = np.linspace(0.2, 0.8, num_generators)
    y_col = np.linspace(0.2, 0.8, num_collectors)
    y_treat = np.linspace(0.2, 0.8, num_treatments)

    # Plot nodes
    plt.scatter([0.2] * num_generators, y_gen, s=200, c="green", label="Generators")
    plt.scatter([0.5] * num_collectors, y_col, s=200, c="blue", label="Collectors")
    plt.scatter([0.8] * num_treatments, y_treat, s=200, c="red", label="Treatment")

    # Plot connections with width proportional to volume
    max_volume = max(
        max(generator_volumes.values()),
        max(collector_volumes.values()),
        max(treatment_volumes.values()),
    )

    # Generator to Collector flows
    for i, (gen, gen_vol) in enumerate(generator_volumes.items()):
        for j, (col, col_vol) in enumerate(collector_volumes.items()):
            width = 2 * gen_vol / max_volume
            plt.plot(
                [0.2, 0.5], [y_gen[i], y_col[j]], "gray", alpha=0.3, linewidth=width
            )

    # Collector to Treatment flows
    for i, (col, col_vol) in enumerate(collector_volumes.items()):
        for j, (treat, treat_vol) in enumerate(treatment_volumes.items()):
            width = 2 * col_vol / max_volume
            plt.plot(
                [0.5, 0.8], [y_col[i], y_treat[j]], "gray", alpha=0.3, linewidth=width
            )

    # Add labels
    for i, (name, vol) in enumerate(generator_volumes.items()):
        plt.annotate(f"{name}\n{vol:.1f}m³", (0.15, y_gen[i]), ha="right", va="center")

    for i, (name, vol) in enumerate(collector_volumes.items()):
        plt.annotate(f"{name}\n{vol:.1f}m³", (0.45, y_col[i]), ha="right", va="center")

    for i, (name, vol) in enumerate(treatment_volumes.items()):
        plt.annotate(f"{name}\n{vol:.1f}m³", (0.85, y_treat[i]), ha="left", va="center")

    plt.title("Material Flow Analysis")
    plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=3)
    plt.axis("off")

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_generation_trends(
    generation_history: Dict, save_path: str = "plots/generation_trends.png"
):
    """Create visualization of waste generation trends over time."""
    plt.figure(figsize=(10, 6))

    for generator, history in generation_history.items():
        total_volumes = []
        for t_idx in range(len(history["timestamps"])):
            total = sum(
                volumes[t_idx]
                for volumes in history["total_generated"].values()
                if len(volumes) > t_idx
            )
            total_volumes.append(total)

        plt.plot(
            history["timestamps"],
            total_volumes,
            label=generator,
            marker="o",
            markersize=4,
        )

    plt.title("Waste Generation Trends")
    plt.xlabel("Time")
    plt.ylabel("Volume (m³)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_collection_efficiency(
    collection_history: Dict, save_path: str = "plots/collection_efficiency.png"
):
    """Create visualization of collection efficiency over time."""
    plt.figure(figsize=(10, 6))

    for collector, history in collection_history.items():
        if history["efficiency"]:
            plt.plot(
                history["timestamps"],
                history["efficiency"],
                label=collector,
                marker="s",
                markersize=4,
            )

    plt.title("Collection Efficiency Over Time")
    plt.xlabel("Time")
    plt.ylabel("Efficiency")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_processing_volume(
    processing_history: Dict, save_path: str = "plots/processing_volume.png"
):
    """Create visualization of processing volume over time."""
    plt.figure(figsize=(10, 6))

    for treatment, history in processing_history.items():
        if history["processed"]["total"]:
            plt.plot(
                history["timestamps"],
                history["processed"]["total"],
                label=treatment,
                marker="^",
                markersize=4,
            )

    plt.title("Processing Volume Over Time")
    plt.xlabel("Time")
    plt.ylabel("Volume (m³)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_system_efficiency(
    processing_history: Dict, save_path: str = "plots/system_efficiency.png"
):
    """Create visualization of system efficiency metrics."""
    plt.figure(figsize=(10, 6))

    for treatment, history in processing_history.items():
        if history["operational"]["conversion_rate"]:
            plt.plot(
                history["timestamps"],
                history["operational"]["conversion_rate"],
                label=f"{treatment} Efficiency",
                marker="*",
                markersize=4,
            )

    plt.title("System Efficiency Metrics")
    plt.xlabel("Time")
    plt.ylabel("Efficiency Rate")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_cumulative_analysis(
    generation_history: Dict,
    collection_history: Dict,
    processing_history: Dict,
    save_path: str = "plots/cumulative_analysis.png",
):
    """Create visualization of cumulative volume analysis."""
    plt.figure(figsize=(10, 6))

    # Calculate all unique timestamps
    all_timestamps = set()
    for history in generation_history.values():
        all_timestamps.update(history["timestamps"])
    for history in collection_history.values():
        all_timestamps.update(history["timestamps"])
    for history in processing_history.values():
        all_timestamps.update(history["timestamps"])

    timestamps = sorted(list(all_timestamps))
    gen_cum = []
    col_cum = []
    proc_cum = []

    # Calculate cumulative volumes
    for t in timestamps:
        gen_total = sum(
            sum(vol[i] for vol in history["total_generated"].values())
            for name, history in generation_history.items()
            for i, ts in enumerate(history["timestamps"])
            if ts <= t
        )
        gen_cum.append(gen_total)

        col_total = sum(
            sum(vol[i] for vol in history["collected_volumes"].values())
            for name, history in collection_history.items()
            for i, ts in enumerate(history["timestamps"])
            if ts <= t
        )
        col_cum.append(col_total)

        proc_total = sum(
            sum(
                history["processed"]["total"][i]
                for i, ts in enumerate(history["timestamps"])
                if ts <= t
            )
            for name, history in processing_history.items()
        )
        proc_cum.append(proc_total)

    plt.plot(timestamps, gen_cum, label="Generated", linewidth=2)
    plt.plot(timestamps, col_cum, label="Collected", linewidth=2)
    plt.plot(timestamps, proc_cum, label="Processed", linewidth=2)

    plt.title("Cumulative Volume Analysis")
    plt.xlabel("Time")
    plt.ylabel("Cumulative Volume (m³)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()


def plot_production_analysis(
    demand_history: List[float],
    production_history: List[float],
    save_path: str = "plots/production_analysis.png",
):
    """Create visualization of production analysis."""
    plt.figure(figsize=(10, 6))

    plt.plot(demand_history, label="Demand", marker="o", markersize=4)
    plt.plot(production_history, label="Production", marker="x", markersize=4)

    cumulative_production = np.cumsum(production_history)
    plt.plot(
        cumulative_production,
        label="Total Products Created",
        linestyle="--",
        linewidth=2,
    )

    plt.title("Production Analysis")
    plt.xlabel("Time")
    plt.ylabel("Volume (m³)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight", dpi=300)
    plt.close()
