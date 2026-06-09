import plotly.graph_objects as go
from typing import Dict

from config.constants import (
    MFA_MIN_FLOW_VOLUME_M3,
    MFA_MIN_NODE_VOLUME_M3,
    PLOTS_ROOT,
    SANKEY_HEIGHT_PX,
    WIDE_EXPORT_WIDTH_PX,
)
from visualization.visualization_utils import safe_write_image

# Sankey node colors keyed by pipeline stage.
NODE_COLORS = {
    'generator': '#2ecc71',    # Green
    'collector': '#3498db',    # Blue
    'treatment': '#9b59b6',    # Purple
    'product': '#e67e22'       # Orange
}


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

def _get_product_volumes(state) -> Dict:
    """Sum true per-operator product output (m³) across treatment operators.

    Sourced from each operator's ``product_volumes`` -- the real cumulative
    output counters -- rather than the retired demand-ceiling state, so the
    Sankey reports actual production with no ceiling cap.
    """
    totals = {"MDF": 0.0, "Particle Board": 0.0, "OSB": 0.0}
    label_by_key = {"mdf": "MDF", "particle_board": "Particle Board", "osb": "OSB"}
    for operator in state.treatment_operators:
        for key, label in label_by_key.items():
            totals[label] += operator.product_volumes.get(key, 0.0)
    return totals

def get_volumes(generation_history: Dict, collection_history: Dict, processing_history: Dict, state):
    """Calculate volumes for each stage - now includes all treatment storage types"""
    return (
        _get_generator_volumes(generation_history),
        _get_collector_volumes(collection_history),
        _get_treatment_volumes(processing_history),
        _get_product_volumes(state)
    )

def _filter_volumes(volumes: Dict, min_volume: float = MFA_MIN_NODE_VOLUME_M3) -> Dict:
    """Filter out entities with minimal volumes"""
    return {k: v for k, v in volumes.items() if v >= min_volume}

def _create_nodes(generators: Dict, collectors: Dict, treatments: Dict, products: Dict):
    """Create node labels and colors"""
    labels = []
    node_colors = []

    gen_start = len(labels)
    for name, volume in generators.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(NODE_COLORS['generator'])

    col_start = len(labels)
    for name, volume in collectors.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(NODE_COLORS['collector'])

    treat_start = len(labels)
    for name, volume in treatments.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(NODE_COLORS['treatment'])

    prod_start = len(labels)
    for name, volume in products.items():
        labels.append(f"{name}\n{format_volume(volume)}")
        node_colors.append(NODE_COLORS['product'])
    
    return labels, node_colors, gen_start, col_start, treat_start, prod_start

# Sankey link colors keyed by transport method. inter_region_transport is the
# treatment-pulled cross-region repositioning hop (collector -> collector); it gets a
# distinct orange so it reads as a separate flow from ordinary collection and intake.
LINK_COLORS = {
    "collection_vehicle": "rgba(46, 204, 113, 0.4)",      # generator -> collector (green)
    "inter_region_transport": "rgba(230, 126, 34, 0.7)",  # collector -> collector (orange)
    "treatment_intake": "rgba(155, 89, 182, 0.4)",        # collector -> treatment (purple)
}
PRODUCT_LINK_COLOR = "rgba(128, 128, 128, 0.4)"           # treatment -> product (neutral grey)


def _create_flows(transport_flows: list, labels: list):
    """Create Sankey links from logged transport flows.

    Resolves each flow's entity name to its node index by EXACT name, not substring
    containment. Node labels are "<name>\n<volume>", so the name is the first line.
    Substring matching mis-routes flows when entity names share a prefix (e.g.
    col_x_1 is a substring of col_x_10), which breaks once a region holds more than
    one node of a type. Also returns a per-link color array so each transport method
    renders in its own colour.
    """
    sources, targets, values, link_colors = [], [], [], []

    name_to_index = {label.split("\n", 1)[0]: i for i, label in enumerate(labels)}

    flow_matrix = {}
    for flow in transport_flows:
        source_index = name_to_index.get(flow["source_name"])
        target_index = name_to_index.get(flow["target_name"])
        if source_index is None or target_index is None:
            continue
        key = (source_index, target_index)
        entry = flow_matrix.setdefault(
            key, {"volume": 0.0, "method": flow.get("transport_method")}
        )
        entry["volume"] += flow["volume"]

    for (source_index, target_index), entry in flow_matrix.items():
        if entry["volume"] >= MFA_MIN_FLOW_VOLUME_M3 and source_index != target_index:
            sources.append(source_index)
            targets.append(target_index)
            values.append(entry["volume"])
            link_colors.append(LINK_COLORS.get(entry["method"], PRODUCT_LINK_COLOR))

    return sources, targets, values, link_colors

def create_sankey(generator_volumes: Dict, collector_volumes: Dict,
                  treatment_volumes: Dict, product_volumes: Dict, state):
    min_volume = MFA_MIN_NODE_VOLUME_M3
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
    
    transport_flows = state.transport_flows
    sources, targets, values, link_colors = _create_flows(transport_flows, labels)

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
                link_colors.append(PRODUCT_LINK_COLOR)
    
    n_gen = len(generators)
    n_col = len(collectors)
    n_treat = len(treatments)
    n_prod = len(products)
    
    x = [0.0]*n_gen + [0.33]*n_col + [0.66]*n_treat + [1.0]*n_prod
    y = []
    for count in (n_gen, n_col, n_treat, n_prod):
        y += [(i+1)/(count+1) for i in range(count)]
    
    return labels, node_colors, sources, targets, values, link_colors, x, y

def create_material_flow_analysis(generation_history: Dict, collection_history: Dict,
                                  processing_history: Dict,
                                  state,
                                  scenario_name: str = None,
                                  inventory_policy: str = None,
                                  stock_strategy: str = None,
                                  save_path: str = None):
    """Create material flow analysis visualization with fixed node columns"""

    if save_path is None:
        suffix = ""
        if scenario_name and inventory_policy and stock_strategy:
            suffix = f"_{scenario_name}_{inventory_policy}_{stock_strategy}"
        save_path = f"{PLOTS_ROOT}/material_flow_analysis{suffix}.html"

    gen_vol, col_vol, treat_vol, prod_vol = get_volumes(
        generation_history, collection_history, processing_history, state
    )

    labels, node_colors, sources, targets, values, link_colors, x, y = create_sankey(
        gen_vol, col_vol, treat_vol, prod_vol, state
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
            "color": link_colors
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
        height=SANKEY_HEIGHT_PX,
        margin={"l": 50, "r": 50, "t": 50, "b": 90}
    )

    fig.add_annotation(
        text=(
            "Flow type: "
            "<span style='color:#2ecc71'>&#9632;</span> collection&nbsp;&nbsp;&nbsp;"
            "<span style='color:#e67e22'>&#9632;</span> inter-region transit&nbsp;&nbsp;&nbsp;"
            "<span style='color:#9b59b6'>&#9632;</span> treatment intake&nbsp;&nbsp;&nbsp;"
            "<span style='color:#808080'>&#9632;</span> production"
        ),
        xref="paper", yref="paper", x=0.0, y=-0.1,
        xanchor="left", showarrow=False, font={"size": 10}
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
    if safe_write_image(fig, pdf_path, height=SANKEY_HEIGHT_PX, width=WIDE_EXPORT_WIDTH_PX):
        print(f"PDF version saved to {pdf_path}")

    return save_path
