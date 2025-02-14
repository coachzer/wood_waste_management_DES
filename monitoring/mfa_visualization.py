import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
from typing import Dict, List
from models.enums import WasteType


def _calculate_volumes(
    generation_history: Dict, collection_history: Dict, processing_history: Dict
):
    """Calculate volumes for each stage of the material flow."""
    generator_volumes = {
        generator: sum(
            volumes[-1] if volumes else 0
            for volumes in history["total_generated"].values()
        )
        for generator, history in generation_history.items()
    }

    collector_volumes = {
        collector: sum(
            volumes[-1] if volumes else 0
            for volumes in history["collected_volumes"].values()
        )
        for collector, history in collection_history.items()
    }

    treatment_volumes = {
        treatment: (
            history["processed"]["total"][-1] if history["processed"]["total"] else 0
        )
        for treatment, history in processing_history.items()
    }

    return generator_volumes, collector_volumes, treatment_volumes


def _calculate_product_data(processing_history: Dict):
    """Calculate product volumes and counts."""
    product_volumes = {waste_type: 0 for waste_type in WasteType}
    product_counts = {waste_type: 0 for waste_type in WasteType}

    for history in processing_history.values():
        for waste_type, volumes in history["processed"]["by_type"].items():
            if volumes:
                product_volumes[waste_type] += volumes[-1]
                product_counts[waste_type] += sum(1 for v in volumes if v > 0)

    return product_volumes, product_counts


def _create_nodes(
    generator_volumes: Dict,
    collector_volumes: Dict,
    treatment_volumes: Dict,
    product_volumes: Dict,
    product_counts: Dict,
):
    """Create nodes for the Sankey diagram."""
    labels, node_colors = [], []

    generator_start_idx = len(labels)
    for generator, volume in generator_volumes.items():
        labels.append(f"{generator}\n{volume:.1f}m³")
        node_colors.append("green")

    collector_start_idx = len(labels)
    for collector, volume in collector_volumes.items():
        labels.append(f"{collector}\n{volume:.1f}m³")
        node_colors.append("blue")

    treatment_start_idx = len(labels)
    for treatment, volume in treatment_volumes.items():
        labels.append(f"{treatment}\n{volume:.1f}m³")
        node_colors.append("red")

    product_start_idx = len(labels)
    max_count = max(product_counts.values()) if product_counts.values() else 1

    for waste_type, volume in product_volumes.items():
        if volume > 0:
            count = product_counts[waste_type]
            labels.append(
                f"Product: {waste_type.value}\n{volume:.1f}m³\n(Created {count} times)"
            )
            node_colors.append("purple")

    return (
        labels,
        node_colors,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        product_start_idx,
        max_count,
    )


def _create_flows(
    generator_volumes: Dict,
    collector_volumes: Dict,
    treatment_volumes: Dict,
    product_volumes: Dict,
    product_counts: Dict,
    processing_history: Dict,
    generator_start_idx: int,
    collector_start_idx: int,
    treatment_start_idx: int,
    product_start_idx: int,
    max_count: float,
):
    """Create flows for the Sankey diagram."""
    source, target, value = [], [], []

    # Generator to Collector flows
    for i, (gen, gen_vol) in enumerate(generator_volumes.items()):
        for j in range(len(collector_volumes)):
            source.append(generator_start_idx + i)
            target.append(collector_start_idx + j)
            value.append(gen_vol)

    # Collector to Treatment flows
    for i, (col, col_vol) in enumerate(collector_volumes.items()):
        for j in range(len(treatment_volumes)):
            source.append(collector_start_idx + i)
            target.append(treatment_start_idx + j)
            value.append(col_vol)

    # Treatment to Product flows
    product_idx_map = {
        waste_type: product_start_idx + i
        for i, waste_type in enumerate(
            waste_type for waste_type, vol in product_volumes.items() if vol > 0
        )
    }

    for i, treatment in enumerate(treatment_volumes.keys()):
        history = processing_history[treatment]
        for waste_type, volumes in history["processed"]["by_type"].items():
            if volumes and waste_type in product_idx_map:
                source.append(treatment_start_idx + i)
                target.append(product_idx_map[waste_type])
                count = product_counts[waste_type]
                count_factor = count / max_count
                value.append(volumes[-1] * (1 + count_factor))

    return source, target, value


def create_material_flow_analysis(
    generation_history: Dict,
    collection_history: Dict,
    processing_history: Dict,
    save_path: str = "plots/material_flow_analysis.html",
):
    """
    Create a Sankey diagram visualization of material flows through the waste management system.
    Shows flows between generators, collectors, treatment facilities, and final products.
    """
    generator_volumes, collector_volumes, treatment_volumes = _calculate_volumes(
        generation_history, collection_history, processing_history
    )

    product_volumes, product_counts = _calculate_product_data(processing_history)

    (
        labels,
        node_colors,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        product_start_idx,
        max_count,
    ) = _create_nodes(
        generator_volumes,
        collector_volumes,
        treatment_volumes,
        product_volumes,
        product_counts,
    )

    source, target, value = _create_flows(
        generator_volumes,
        collector_volumes,
        treatment_volumes,
        product_volumes,
        product_counts,
        processing_history,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        product_start_idx,
        max_count,
    )

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=labels,
                    color=node_colors,
                ),
                link=dict(source=source, target=target, value=value),
            )
        ]
    )

    fig.update_layout(title_text="Material Flow Analysis", font_size=10, height=800)
    fig.write_html(save_path)


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
