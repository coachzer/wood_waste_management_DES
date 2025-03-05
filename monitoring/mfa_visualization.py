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
    volume_threshold: float = 0.1,  # Filter out nodes with volumes below this threshold
):
    """Create nodes for the Sankey diagram with volume-based filtering and improved organization."""
    labels, node_colors = [], []

    # Helper function to format volume label with metric prefix
    def format_volume(volume: float) -> str:
        if volume >= 1000:
            return f"{volume/1000:.1f}km³"
        return f"{volume:.1f}m³"

    # Filter and sort generators by volume
    filtered_generators = {
        k: v for k, v in generator_volumes.items() if v >= volume_threshold
    }
    sorted_generators = dict(
        sorted(filtered_generators.items(), key=lambda x: x[1], reverse=True)
    )

    generator_start_idx = len(labels)
    for generator, volume in sorted_generators.items():
        labels.append(f"{generator}<br>{format_volume(volume)}")
        node_colors.append("rgba(0, 128, 0, 0.7)")  # Semi-transparent green

    # Filter and sort collectors
    filtered_collectors = {
        k: v for k, v in collector_volumes.items() if v >= volume_threshold
    }
    sorted_collectors = dict(
        sorted(filtered_collectors.items(), key=lambda x: x[1], reverse=True)
    )

    collector_start_idx = len(labels)
    for collector, volume in sorted_collectors.items():
        labels.append(f"{collector}<br>{format_volume(volume)}")
        node_colors.append("rgba(0, 0, 255, 0.7)")  # Semi-transparent blue

    # Filter and sort treatment facilities
    filtered_treatments = {
        k: v for k, v in treatment_volumes.items() if v >= volume_threshold
    }
    sorted_treatments = dict(
        sorted(filtered_treatments.items(), key=lambda x: x[1], reverse=True)
    )

    treatment_start_idx = len(labels)
    for treatment, volume in sorted_treatments.items():
        labels.append(f"{treatment}<br>{format_volume(volume)}")
        node_colors.append("rgba(255, 0, 0, 0.7)")  # Semi-transparent red

    product_start_idx = len(labels)
    max_count = max(product_counts.values()) if product_counts.values() else 1

    # Filter and sort products
    filtered_products = {
        k: v for k, v in product_volumes.items() if v >= volume_threshold
    }
    for waste_type, volume in filtered_products.items():
        if volume > 0:
            count = product_counts[waste_type]
            labels.append(
                f"Product: {waste_type.value}<br>{format_volume(volume)}<br>Created {count} times"
            )
            node_colors.append("rgba(128, 0, 128, 0.7)")  # Semi-transparent purple

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

    # Update layout with improved styling and interactivity
    fig.update_layout(
        title=dict(
            text="Material Flow Analysis", font=dict(size=16), x=0.5, xanchor="center"
        ),
        font=dict(size=10),
        height=800,
        hovermode="x",
        plot_bgcolor="rgba(255,255,255,0.9)",
        paper_bgcolor="rgba(255,255,255,0.9)",
    )
    fig.write_html(save_path)
