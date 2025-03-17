import plotly.graph_objects as go
from typing import Dict
from models.enums import WasteType
from models.state import SimulationState

def _calculate_volumes(
    generation_history: Dict, collection_history: Dict, processing_history: Dict
):
    """Calculate volumes for each stage of the material flow."""
    # Calculate generator volumes
    generator_volumes = {
        generator: sum(
            volumes[-1] if volumes else 0
            for volumes in history["total_generated"].values()
        )
        for generator, history in generation_history.items()
    }

    # Calculate collector volumes
    collector_volumes = {
        collector: sum(
            volumes[-1] if volumes else 0
            for volumes in history["collected_volumes"].values()
        )
        for collector, history in collection_history.items()
    }

    # Calculate treatment volumes and product volumes separately
    treatment_volumes = {}
    product_by_type = {}
    
    for treatment, history in processing_history.items():
        # Get total processed volume for treatment node
        total_volume = history["processed"]["total"][-1] if history["processed"]["total"] else 0
        treatment_volumes[treatment] = total_volume
        
        # Get volumes by product type for product nodes
        products = history["products"]
        by_type = products.get("by_type", {})
        for product_type, volumes in by_type.items():
            if product_type not in product_by_type:
                product_by_type[product_type] = []
            if volumes:
                product_by_type[product_type].append(volumes[-1])

    # Aggregate product volumes by type
    processed_volumes = {
        product_type: sum(volumes)
        for product_type, volumes in product_by_type.items()
    }

    return generator_volumes, collector_volumes, treatment_volumes, processed_volumes

def _get_demand_volumes():
    """Get demand volumes from demand.json."""
    import json
    
    with open('data/demand.json', 'r') as f:
        demand_data = json.load(f)
    
    target_products = [WasteType.WOODEN_PACKAGING, WasteType.PAPER_PACKAGING, WasteType.WOODEN_FURNITURE]
    demand_volumes = {}
    for product in target_products:
        key = product.value.lower()
        if key in demand_data['national_demand']:
            demand_volumes[product] = demand_data['national_demand'][key]
    
    return demand_volumes

def _create_nodes(
    generator_volumes: Dict,
    collector_volumes: Dict,
    treatment_volumes: Dict,
    demand_volumes: Dict,
    processed_volumes: Dict,
    volume_threshold: float
):
    """Create nodes for the Sankey diagram."""
    labels, node_colors = [], []

    def format_volume(volume: float) -> str:
        """Format volume with appropriate metric prefix"""
        return f"{volume/1000:.1f}km³" if volume >= 1000 else f"{volume:.1f}m³"

    def sort_by_volume(volumes: Dict) -> Dict:
        """Sort volumes dictionary by value in descending order"""
        filtered = {k: v for k, v in volumes.items() if v >= volume_threshold}
        return dict(sorted(filtered.items(), key=lambda x: x[1], reverse=True))

    # Sort volumes for each stage
    sorted_generators = sort_by_volume(generator_volumes)
    sorted_collectors = sort_by_volume(collector_volumes)
    sorted_treatments = sort_by_volume(treatment_volumes)

    # Node colors for each stage
    NODE_COLORS = {
        'generator': "rgba(46, 204, 113, 0.7)",    # Green
        'collector': "rgba(52, 152, 219, 0.7)",    # Blue
        'treatment': "rgba(155, 89, 182, 0.7)",    # Purple
        'demand': "rgba(230, 126, 34, 0.7)"        # Orange
    }

    # Add generator nodes
    generator_start_idx = len(labels)
    for generator, volume in sorted_generators.items():
        labels.append(f"{generator}<br>{format_volume(volume)}")
        node_colors.append(NODE_COLORS['generator'])

    # Add collector nodes
    collector_start_idx = len(labels)
    for collector, volume in sorted_collectors.items():
        labels.append(f"{collector}<br>{format_volume(volume)}")
        node_colors.append(NODE_COLORS['collector'])

    # Add treatment nodes
    treatment_start_idx = len(labels)
    for treatment, volume in sorted_treatments.items():
        labels.append(f"{treatment}<br>{format_volume(volume)}")
        node_colors.append(NODE_COLORS['treatment'])

    # Add demand nodes with actual processed volumes
    # Get current production from simulation state
    state = SimulationState.get_instance()
    demand_start_idx = len(labels)
    target_products = [WasteType.WOODEN_PACKAGING, WasteType.PAPER_PACKAGING, WasteType.WOODEN_FURNITURE]
    
    for product in target_products:
        target_volume = demand_volumes.get(product, 0)
        # Get actual production from simulation state
        product_type = product.value.lower()
        current_volume = state.total_products.get(product_type, 0)
        fulfillment = (current_volume / target_volume * 100) if target_volume > 0 else 0

        labels.append(
            f"{product.value}<br>"
            f"Target: {format_volume(target_volume)}<br>"
            f"Current: {format_volume(current_volume)}<br>"
            f"({fulfillment:.1f}%)"
        )
        node_colors.append(NODE_COLORS['demand'])

    return (
        labels,
        node_colors,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        demand_start_idx,
        sorted_generators,
        sorted_collectors,
        sorted_treatments
    )

def _create_flows(
    sorted_generators: Dict,
    sorted_collectors: Dict,
    sorted_treatments: Dict,
    processing_history: Dict,
    generator_start_idx: int,
    collector_start_idx: int,
    treatment_start_idx: int,
    demand_start_idx: int,
    demand_volumes: Dict,
    volume_threshold: float
):
    """Create flows for the Sankey diagram while preserving volume proportions."""
    source, target, value = [], [], []

    # Generator to Collector flows - distribute proportionally based on collection history
    total_collected = sum(sorted_collectors.values())

    if total_collected > 0:
        for gen_idx, (gen, gen_vol) in enumerate(sorted_generators.items()):
            for col_idx, (col, col_vol) in enumerate(sorted_collectors.items()):
                # Determine proportional allocation from generator to collector
                allocation = (col_vol / total_collected) * gen_vol
                if allocation >= volume_threshold:
                    source.append(generator_start_idx + gen_idx)
                    target.append(collector_start_idx + col_idx)
                    value.append(allocation)
    else:  # If no collectors, generators send directly to treatment
        total_treated = sum(sorted_treatments.values())
        if total_treated > 0:
            for gen_idx, (gen, gen_vol) in enumerate(sorted_generators.items()):
                for treat_idx, (treat, treat_vol) in enumerate(sorted_treatments.items()):
                    allocation = (treat_vol / total_treated) * gen_vol
                    if allocation >= volume_threshold:
                        source.append(generator_start_idx + gen_idx)
                        target.append(treatment_start_idx + treat_idx)
                        value.append(allocation)

    # Collector to Treatment flows - distribute proportionally based on processing history
    total_treated = sum(sorted_treatments.values())

    if total_treated > 0:
        for col_idx, (col, col_vol) in enumerate(sorted_collectors.items()):
            for treat_idx, (treat, treat_vol) in enumerate(sorted_treatments.items()):
                allocation = (treat_vol / total_treated) * col_vol
                if allocation >= volume_threshold:
                    source.append(collector_start_idx + col_idx)
                    target.append(treatment_start_idx + treat_idx)
                    value.append(allocation)
    else:  # If no treatments, collectors send directly to demand
        for col_idx, (col, col_vol) in enumerate(sorted_collectors.items()):
            for demand_idx, (product, demand_vol) in enumerate(demand_volumes.items()):
                allocation = (demand_vol / sum(demand_volumes.values())) * col_vol
                if allocation >= volume_threshold:
                    source.append(collector_start_idx + col_idx)
                    target.append(demand_start_idx + demand_idx)
                    value.append(allocation)

    # Treatment to Demand flows - use actual production from SimulationState
    state = SimulationState.get_instance()
    total_treatment_volume = sum(sorted_treatments.values())
    
    if total_treatment_volume > 0:
        for demand_idx, product in enumerate(demand_volumes.keys()):
            product_type = product.value.lower()
            actual_production = state.total_products.get(product_type, 0)
            
            if actual_production >= volume_threshold:
                # Distribute the production across treatment facilities proportionally
                for treat_idx, (treat, treat_vol) in enumerate(sorted_treatments.items()):
                    # Calculate this treatment's contribution based on its share of total treatment
                    treatment_share = treat_vol / total_treatment_volume
                    flow_value = actual_production * treatment_share
                    
                    if flow_value >= volume_threshold:
                        source.append(treatment_start_idx + treat_idx)
                        target.append(demand_start_idx + demand_idx)
                        value.append(flow_value)

    return source, target, value

def create_material_flow_analysis(
    generation_history: Dict,
    collection_history: Dict,
    processing_history: Dict,
    save_path: str = "plots/material_flow_analysis.html",
):
    """Create a Sankey diagram visualization of material flows through the waste management system."""
    # Calculate volumes for each stage and processed volumes by type
    generator_volumes, collector_volumes, treatment_volumes, processed_volumes = _calculate_volumes(
        generation_history, collection_history, processing_history
    )
    
    # Get target demand volumes
    demand_volumes = _get_demand_volumes()

    # Create nodes with consistent volume threshold
    volume_threshold = 0.1
    (
        labels,
        node_colors,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        demand_start_idx,
        sorted_generators,
        sorted_collectors,
        sorted_treatments
    ) = _create_nodes(
        generator_volumes,
        collector_volumes,
        treatment_volumes,
        demand_volumes,
        processed_volumes,  # Add processed volumes
        volume_threshold
    )

    # Create flows between stages
    source, target, value = _create_flows(
        sorted_generators,
        sorted_collectors,
        sorted_treatments,
        processing_history,
        generator_start_idx,
        collector_start_idx,
        treatment_start_idx,
        demand_start_idx,
        demand_volumes,
        volume_threshold
    )

    # Create and configure the Sankey diagram
    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=labels,
                    color=node_colors,
                    hoverlabel=dict(
                        bgcolor="white",
                        font_size=12,
                        font_family="Arial"
                    ),
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value,
                    hoverlabel=dict(
                        bgcolor="white",
                        font_size=12,
                        font_family="Arial"
                    ),
                    hovertemplate="From: %{source.label}<br>To: %{target.label}<br>Volume: %{value:.2f}m³<extra></extra>"
                ),
            )
        ]
    )

    # Update layout
    fig.update_layout(
        title=dict(
            text="Material Flow Analysis",
            font=dict(size=16),
            x=0.5,
            xanchor="center"
        ),
        font=dict(size=12),
        height=800,
        hovermode="x",
        plot_bgcolor="white",
        paper_bgcolor="white"
    )
    fig.write_html(save_path)
