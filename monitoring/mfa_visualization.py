import json
import plotly.graph_objects as go
from typing import Dict, List, Tuple
from models.enums import OutputType
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

    collector_volumes = {}
    
    # First try to get volumes from maximum recorded values
    for collector, history in collection_history.items():
        total_volume = 0
        for _, volumes in history["collected_volumes"].items():
            if volumes:
                max_volume = max(volumes) if volumes else 0
                total_volume += max_volume
        collector_volumes[collector] = total_volume
    
    # If all collector volumes are 0, estimate based on treatment processing by region
    if sum(collector_volumes.values()) == 0:
        print("[MFA DEBUG] All collector volumes are 0, estimating from treatment activity")
        region_to_collector = {}
        for collector_name in collection_history.keys():
            # Extract region from collector name (e.g., "col_goriska_1" -> "goriska")
            region = collector_name.replace("col_", "").replace("_1", "")
            region_to_collector[region] = collector_name
        
        # Estimate collector volumes from treatment processing
        for treatment_name, treatment_history in processing_history.items():
            if "processed" in treatment_history and "total" in treatment_history["processed"]:
                total_processed = treatment_history["processed"]["total"]
                if total_processed and len(total_processed) > 0:
                    max_processed = max(total_processed)
                    # Try to match treatment to region and assign to collector
                    for region, collector_name in region_to_collector.items():
                        if region in treatment_name.lower():
                            collector_volumes[collector_name] = max(
                                collector_volumes.get(collector_name, 0), 
                                max_processed * 0.8  # Assume 80% of processing came through collectors
                            )
                            break

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

    return generator_volumes, collector_volumes, treatment_volumes

def _get_demand_volumes():
    """Get demand volumes from demand.json."""
    
    with open('data/demand.json', 'r') as f:
        demand_data = json.load(f)
    
    target_products = [OutputType.WOODEN_PACKAGING, OutputType.PAPER_PACKAGING, OutputType.WOODEN_FURNITURE]
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
    target_products = [OutputType.WOODEN_PACKAGING, OutputType.PAPER_PACKAGING, OutputType.WOODEN_FURNITURE]
    
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

# Helper function to create flows from generators to collectors
def _generator_to_collector_flows(
    sorted_generators: Dict,
    sorted_collectors: Dict,
    generator_start_idx: int,
    collector_start_idx: int,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    sources, targets, values = [], [], []
    total_collected = sum(sorted_collectors.values())
    if total_collected > 0:
        for gen_idx, (_, gen_vol) in enumerate(sorted_generators.items()):
            for col_idx, (_, col_vol) in enumerate(sorted_collectors.items()):
                allocation = (col_vol / total_collected) * gen_vol
                if allocation >= volume_threshold:
                    sources.append(generator_start_idx + gen_idx)
                    targets.append(collector_start_idx + col_idx)
                    values.append(allocation)
    return sources, targets, values

# Fallback: generator flows directly to treatment if no collectors exist.
def _generator_to_treatment_flows(
    sorted_generators: Dict,
    sorted_treatments: Dict,
    generator_start_idx: int,
    treatment_start_idx: int,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    sources, targets, values = [], [], []
    total_treated = sum(sorted_treatments.values())
    if total_treated > 0:
        for gen_idx, (_, gen_vol) in enumerate(sorted_generators.items()):
            for treat_idx, (_, treat_vol) in enumerate(sorted_treatments.items()):
                allocation = (treat_vol / total_treated) * gen_vol
                if allocation >= volume_threshold:
                    sources.append(generator_start_idx + gen_idx)
                    targets.append(treatment_start_idx + treat_idx)
                    values.append(allocation)
    return sources, targets, values

# Create flows from collectors to treatments
def _collector_to_treatment_flows(
    sorted_collectors: Dict,
    sorted_treatments: Dict,
    collector_start_idx: int,
    treatment_start_idx: int,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    sources, targets, values = [], [], []
    total_treated = sum(sorted_treatments.values())
    if total_treated > 0:
        for col_idx, (_, col_vol) in enumerate(sorted_collectors.items()):
            for treat_idx, (_, treat_vol) in enumerate(sorted_treatments.items()):
                allocation = (treat_vol / total_treated) * col_vol
                if allocation >= volume_threshold:
                    sources.append(collector_start_idx + col_idx)
                    targets.append(treatment_start_idx + treat_idx)
                    values.append(allocation)
    return sources, targets, values

# Fallback: collectors send directly to demand if no treatments exist.
def _collector_to_demand_flows(
    sorted_collectors: Dict,
    demand_volumes: Dict,
    collector_start_idx: int,
    demand_start_idx: int,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    sources, targets, values = [], [], []
    total_demand = sum(demand_volumes.values())
    for col_idx, (_, col_vol) in enumerate(sorted_collectors.items()):
        for demand_idx, (_, demand_vol) in enumerate(demand_volumes.items()):
            allocation = (demand_vol / total_demand) * col_vol
            if allocation >= volume_threshold:
                sources.append(collector_start_idx + col_idx)
                targets.append(demand_start_idx + demand_idx)
                values.append(allocation)
    return sources, targets, values

# Create flows from treatments to demand based on actual production
def _treatment_to_demand_flows(
    sorted_treatments: Dict,
    demand_volumes: Dict,
    treatment_start_idx: int,
    demand_start_idx: int,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    sources, targets, values = [], [], []
    # Get the singleton SimulationState instance (assumed defined elsewhere)
    state = SimulationState.get_instance()
    total_treatment_volume = sum(sorted_treatments.values())
    if total_treatment_volume > 0:
        for demand_idx, product in enumerate(demand_volumes.keys()):
            product_type = product.value.lower()  # Assuming product has a value attribute
            actual_production = state.total_products.get(product_type, 0)
            if actual_production >= volume_threshold:
                for treat_idx, (_, treat_vol) in enumerate(sorted_treatments.items()):
                    treatment_share = treat_vol / total_treatment_volume
                    flow_value = actual_production * treatment_share
                    if flow_value >= volume_threshold:
                        sources.append(treatment_start_idx + treat_idx)
                        targets.append(demand_start_idx + demand_idx)
                        values.append(flow_value)
    return sources, targets, values

# Main function that assembles all flows
def create_flows(
    sorted_generators: Dict,
    sorted_collectors: Dict,
    sorted_treatments: Dict,
    generator_start_idx: int,
    collector_start_idx: int,
    treatment_start_idx: int,
    demand_start_idx: int,
    demand_volumes: Dict,
    volume_threshold: float
) -> Tuple[List[int], List[int], List[float]]:
    """Create flows for the Sankey diagram while preserving volume proportions."""
    src, tgt, val = [], [], []
    
    # Generator flows: use generator -> collector if collectors exist;
    # otherwise, send generators directly to treatment.
    total_collected = sum(sorted_collectors.values())
    if total_collected > 0:
        gen_src, gen_tgt, gen_val = _generator_to_collector_flows(
            sorted_generators, sorted_collectors,
            generator_start_idx, collector_start_idx, volume_threshold
        )
    else:
        gen_src, gen_tgt, gen_val = _generator_to_treatment_flows(
            sorted_generators, sorted_treatments,
            generator_start_idx, treatment_start_idx, volume_threshold
        )
    src.extend(gen_src)
    tgt.extend(gen_tgt)
    val.extend(gen_val)
    
    # Collector flows: use collector -> treatment if treatments exist;
    # otherwise, send collectors directly to demand.
    total_treated = sum(sorted_treatments.values())
    if total_treated > 0:
        col_src, col_tgt, col_val = _collector_to_treatment_flows(
            sorted_collectors, sorted_treatments,
            collector_start_idx, treatment_start_idx, volume_threshold
        )
    else:
        col_src, col_tgt, col_val = _collector_to_demand_flows(
            sorted_collectors, demand_volumes,
            collector_start_idx, demand_start_idx, volume_threshold
        )
    src.extend(col_src)
    tgt.extend(col_tgt)
    val.extend(col_val)
    
    # Treatment to demand flows based on actual production
    treat_src, treat_tgt, treat_val = _treatment_to_demand_flows(
        sorted_treatments, demand_volumes,
        treatment_start_idx, demand_start_idx, volume_threshold
    )
    src.extend(treat_src)
    tgt.extend(treat_tgt)
    val.extend(treat_val)
    
    return src, tgt, val

def create_material_flow_analysis(
    generation_history: Dict,
    collection_history: Dict,
    processing_history: Dict,
    save_path: str = "plots/material_flow_analysis.html",
):
    """Create a Sankey diagram visualization of material flows through the waste management system."""
    # Calculate volumes for each stage and processed volumes by type
    generator_volumes, collector_volumes, treatment_volumes = _calculate_volumes(
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
        volume_threshold
    )

    # Create flows between stages
    source, target, value = create_flows(
        sorted_generators,
        sorted_collectors,
        sorted_treatments,
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
