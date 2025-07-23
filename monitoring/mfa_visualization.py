import plotly.graph_objects as go
from typing import Dict
from models.state import SimulationState


def format_volume(volume: float) -> str:
    """Format volume with appropriate units"""
    if volume >= 1000:
        return f"{volume/1000:.1f}k m³"
    else:
        return f"{volume:.1f} m³"


def _get_generator_volumes(generation_history: Dict) -> Dict:
    """Calculate generator volumes"""
    generator_volumes = {}
    for generator, history in generation_history.items():
        total = 0
        for _, volumes in history.get("total_generated", {}).items():
            if volumes:
                total += volumes[-1]  # Latest cumulative value
        generator_volumes[generator] = total
    return generator_volumes


def _get_collector_volumes(collection_history: Dict) -> Dict:
    """Calculate collector volumes"""
    collector_volumes = {}
    for collector, history in collection_history.items():
        total = 0
        for _, volumes in history.get("collected_volumes", {}).items():
            if volumes:
                total += volumes[-1] if volumes else 0 
        collector_volumes[collector] = total
    return collector_volumes


def _get_treatment_volumes(processing_history: Dict) -> Dict:
    """Calculate treatment volumes"""
    treatment_volumes = {}
    for treatment, history in processing_history.items():
        processed = history.get("processed", {}).get("total", [])
        treatment_volumes[treatment] = processed[-1] if processed else 0
    return treatment_volumes


def _get_product_volumes() -> Dict:
    """Get product volumes from simulation state"""
    state = SimulationState.get_instance()
    return {
        "MDF Fibreboard": state.total_products.get("mdf_fibreboard", 0),
        "Particle Board": state.total_products.get("particle_board", 0),
        "OSB Waferboard": state.total_products.get("osb_waferboard", 0)
    }


def get_volumes(generation_history: Dict, collection_history: Dict, processing_history: Dict):
    """Calculate volumes for each stage - simplified approach"""
    return (
        _get_generator_volumes(generation_history),
        _get_collector_volumes(collection_history), 
        _get_treatment_volumes(processing_history),
        _get_product_volumes()
    )


def _filter_volumes(volumes: Dict, min_volume: float = 1.0) -> Dict:
    """Filter out entities with minimal volumes"""
    return {k: v for k, v in volumes.items() if v >= min_volume}


def _create_nodes(generators: Dict, collectors: Dict, treatments: Dict, products: Dict):
    """Create node labels and colors"""
    labels = []
    node_colors = []
    
    # Define colors for each stage
    COLORS = {
        'generator': '#2ecc71',    # Green
        'collector': '#3498db',    # Blue  
        'treatment': '#9b59b6',    # Purple
        'product': '#e67e22'       # Orange
    }
    
    # Add nodes with their start indices
    gen_start = len(labels)
    for name, volume in generators.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(COLORS['generator'])
    
    col_start = len(labels)
    for name, volume in collectors.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(COLORS['collector'])
    
    treat_start = len(labels)
    for name, volume in treatments.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(COLORS['treatment'])
    
    prod_start = len(labels)
    for name, volume in products.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(COLORS['product'])
    
    return labels, node_colors, gen_start, col_start, treat_start, prod_start


def _add_flow_between_stages(sources: list, targets: list, values: list,
                           stage1_items: Dict, stage2_items: Dict,
                           stage1_start: int, stage2_start: int, min_volume: float):
    """Add flows between two stages"""
    if not stage1_items or not stage2_items:
        return
        
    total_stage2 = sum(stage2_items.values())
    if total_stage2 <= 0:
        return
        
    for i, (name1, vol1) in enumerate(stage1_items.items()):
        for j, (name2, vol2) in enumerate(stage2_items.items()):
            flow = vol1 * (vol2 / total_stage2)
            if flow >= min_volume:
                sources.append(stage1_start + i)
                targets.append(stage2_start + j)
                values.append(flow)


def _create_flows(generators: Dict, collectors: Dict, treatments: Dict, products: Dict,
                 gen_start: int, col_start: int, treat_start: int, prod_start: int, 
                 min_volume: float = 1.0):
    """Create flows between stages"""
    sources, targets, values = [], [], []
    
    # Generator -> Collector flows
    _add_flow_between_stages(sources, targets, values, generators, collectors,
                           gen_start, col_start, min_volume)
    
    # Collector -> Treatment flows  
    _add_flow_between_stages(sources, targets, values, collectors, treatments,
                           col_start, treat_start, min_volume)
    
    # Treatment -> Product flows
    _add_flow_between_stages(sources, targets, values, treatments, products,
                           treat_start, prod_start, min_volume)
    
    return sources, targets, values


def create_sankey(generator_volumes: Dict, collector_volumes: Dict, 
                        treatment_volumes: Dict, product_volumes: Dict):
    """Create a simple Sankey diagram with clear flow chain"""
    
    # Filter out entities with minimal volumes
    min_volume = 1.0
    generators = _filter_volumes(generator_volumes, min_volume)
    collectors = _filter_volumes(collector_volumes, min_volume)
    treatments = _filter_volumes(treatment_volumes, min_volume)
    products = _filter_volumes(product_volumes, min_volume)
    
    # Create nodes
    labels, node_colors, gen_start, col_start, treat_start, prod_start = _create_nodes(
        generators, collectors, treatments, products
    )
    
    # Create flows
    sources, targets, values = _create_flows(
        generators, collectors, treatments, products,
        gen_start, col_start, treat_start, prod_start, min_volume
    )
    
    return labels, node_colors, sources, targets, values


def create_material_flow_analysis(generation_history: Dict, collection_history: Dict, 
                                 processing_history: Dict, 
                                 scenario_name: str = None,
                                 inventory_policy: str = None,
                                 stock_strategy: str = None,
                                 save_path: str = None):
    """Create material flow analysis visualization"""
    
    # Generate scenario-specific filename if not provided
    if save_path is None:
        scenario_suffix = ""
        if scenario_name and inventory_policy and stock_strategy:
            scenario_suffix = f"_{scenario_name}_{inventory_policy}_{stock_strategy}"
        
        save_path = f"plots/material_flow_analysis{scenario_suffix}.html"

    # Get volumes for each stage
    generator_volumes, collector_volumes, treatment_volumes, product_volumes = get_volumes(
        generation_history, collection_history, processing_history
    )
    
    # Create Sankey diagram components
    labels, node_colors, sources, targets, values = create_sankey(
        generator_volumes, collector_volumes, treatment_volumes, product_volumes
    )

    title = "Wood Waste Material Flow Analysis"
    if scenario_name:
        title += f" - {scenario_name}"
    elif inventory_policy and stock_strategy:
        title += f" - {inventory_policy} | {stock_strategy}"
    
    # Create the visualization
    fig = go.Figure(data=[go.Sankey(
        node={
            "pad": 15,
            "thickness": 20,
            "line": {"color": "black", "width": 0.5},
            "label": labels,
            "color": node_colors
        },
        link={
            "source": sources,
            "target": targets,
            "value": values,
            "color": "rgba(128, 128, 128, 0.4)"
        }
    )])
    
    # Update layout
    fig.update_layout(
        title=title,
        font_size=12,
        height=600,
        margin={"l": 50, "r": 50, "t": 50, "b": 50}
    )

    if inventory_policy and stock_strategy:
        fig.add_annotation(
            text=f"Scenario: {scenario_name}<br>Inventory Policy: {inventory_policy}<br>Stock Strategy: {stock_strategy}",
            xref="paper", yref="paper",
            x=0.98, y=0.98,
            showarrow=False,
            font={'size': 10},
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="black",
            borderwidth=1
        )
    
    # Save the plot
    fig.write_html(save_path)
    print(f"Material flow analysis saved to {save_path}")
    
    # Print summary
    total_generated = sum(generator_volumes.values())
    total_collected = sum(collector_volumes.values()) 
    total_treated = sum(treatment_volumes.values())
    total_products = sum(product_volumes.values())
    
    print("\nMaterial Flow Summary:")
    print(f"  Generated: {format_volume(total_generated)}")
    print(f"  Collected: {format_volume(total_collected)}")
    print(f"  Treated: {format_volume(total_treated)}")
    print(f"  Products: {format_volume(total_products)}")
    
    if total_generated > 0:
        collection_efficiency = (total_collected / total_generated) * 100
        treatment_efficiency = (total_treated / total_collected) * 100 if total_collected > 0 else 0
        product_efficiency = (total_products / total_treated) * 100 if total_treated > 0 else 0
        
        print("\nEfficiencies:")
        print(f"  Collection: {collection_efficiency:.1f}%")
        print(f"  Treatment: {treatment_efficiency:.1f}%") 
        print(f"  Production: {product_efficiency:.1f}%")

    return save_path
