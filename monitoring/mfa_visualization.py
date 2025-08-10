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
                total += volumes[-1] 
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
        "MDF": state.total_products.get("mdf", 0),
        "Particle Board": state.total_products.get("particle_board", 0),
        "OSB": state.total_products.get("osb", 0)
    }

def get_volumes(generation_history: Dict, collection_history: Dict, processing_history: Dict):
    """Calculate volumes for each stage - now includes all treatment storage types"""
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
    
    COLORS = {
        'generator': '#2ecc71',    # Green
        'collector': '#3498db',    # Blue  
        'treatment': '#9b59b6',    # Purple
        'product': '#e67e22'       # Orange
    }

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

def _create_flows(transport_flows: list, labels: list):
    """Create flows based on actual transport data"""
    sources, targets, values = [], [], []
    
    flow_matrix = {}
    
    for flow in transport_flows:
        source_name = flow['source_name']
        target_name = flow['target_name']
        volume = flow['volume']
        
        source_idx = None
        target_idx = None
        
        for i, label in enumerate(labels):
            if source_name in label:
                source_idx = i
                break
        
        for i, label in enumerate(labels):
            if target_name in label:
                target_idx = i
                break
        
        if source_idx is not None and target_idx is not None:
            key = (source_idx, target_idx)
            flow_matrix[key] = flow_matrix.get(key, 0) + volume
    
    for (source_idx, target_idx), total_volume in flow_matrix.items():
        if total_volume >= 0.1 and source_idx != target_idx: 
            sources.append(source_idx)
            targets.append(target_idx)
            values.append(total_volume)
    
    print(f"[MFA DEBUG] Created {len(sources)} real transport flows")
    return sources, targets, values

def create_sankey(generator_volumes: Dict, collector_volumes: Dict, 
                  treatment_volumes: Dict, product_volumes: Dict):
    min_volume = 1.0
    generators = _filter_volumes(generator_volumes, min_volume)
    collectors = _filter_volumes(collector_volumes, min_volume)
    treatments = _filter_volumes(treatment_volumes, min_volume)
    products   = _filter_volumes(product_volumes,   min_volume)

    generators = dict(sorted(generators.items()))
    collectors = dict(sorted(collectors.items()))
    treatments = dict(sorted(treatments.items()))
    products = dict(sorted(products.items()))
    
    labels, node_colors, _, _, treat_start, prod_start = _create_nodes(
        generators, collectors, treatments, products
    )
    
    state = SimulationState.get_instance()
    transport_flows = state.transport_flows
    sources, targets, values = _create_flows(transport_flows, labels)
    
    for t_idx, treat_name in enumerate(treatments.keys()):
        op = next((o for o in state.treatment_operators if o.name == treat_name), None)
        if not op:
            continue
        for p_idx, prod_label in enumerate(products.keys()):
            key = prod_label.lower().replace(" ", "_")
            vol = op.product_volumes.get(key, 0.0)
            if vol >= min_volume:
                sources.append(treat_start + t_idx)
                targets.append(prod_start + p_idx)
                values.append(vol)
    
    n_gen = len(generators)
    n_col = len(collectors)
    n_treat = len(treatments)
    n_prod = len(products)
    
    x = [0.0]*n_gen + [0.33]*n_col + [0.66]*n_treat + [1.0]*n_prod
    y = []
    for count in (n_gen, n_col, n_treat, n_prod):
        y += [(i+1)/(count+1) for i in range(count)]
    
    return labels, node_colors, sources, targets, values, x, y

def create_material_flow_analysis(generation_history: Dict, collection_history: Dict, 
                                  processing_history: Dict, 
                                  scenario_name: str = None,
                                  inventory_policy: str = None,
                                  stock_strategy: str = None,
                                  save_path: str = None):
    """Create material flow analysis visualization with fixed node columns"""

    if save_path is None:
        suffix = ""
        if scenario_name and inventory_policy and stock_strategy:
            suffix = f"_{scenario_name}_{inventory_policy}_{stock_strategy}"
        save_path = f"plots/material_flow_analysis{suffix}.html"

    gen_vol, col_vol, treat_vol, prod_vol = get_volumes(
        generation_history, collection_history, processing_history
    )

    labels, node_colors, sources, targets, values, x, y = create_sankey(
        gen_vol, col_vol, treat_vol, prod_vol
    )

    fig = go.Figure(data=[go.Sankey(
        node={
            "pad": 15,
            "thickness": 20,
            "line": {"color": "black", "width": 0.5},
            "label": labels,
            "color": node_colors,
            "x": x,
            "y": y
        },
        link={
            "source": sources,
            "target": targets,
            "value": values,
            "color": "rgba(128, 128, 128, 0.4)"
        }
    )])

    title = "Wood Waste Material Flow Analysis"
    if scenario_name:
        title += f" - {scenario_name}"
    elif inventory_policy and stock_strategy:
        title += f" - {inventory_policy} | {stock_strategy}"

    fig.update_layout(
        title=title,
        font_size=12,
        height=600,
        margin={"l": 50, "r": 50, "t": 50, "b": 50}
    )

    if inventory_policy and stock_strategy:
        fig.add_annotation(
            text=f"Scenario: {scenario_name}<br>Inventory Policy: {inventory_policy}<br>Stock Strategy: {stock_strategy}",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font={'size': 10},
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="black", borderwidth=1
        )

    fig.write_html(save_path)
    print(f"Material flow analysis saved to {save_path}")

    pdf_path = save_path.replace(".html", ".pdf")
    fig.write_image(pdf_path, height=600, width=1600)
    print(f"PDF version saved to {pdf_path}")

    return save_path
