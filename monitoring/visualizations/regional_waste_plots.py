import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from plotly.subplots import make_subplots
from models.enums import RegionType, WasteType
from models.state import SimulationState
import json


def plot_regional_waste_distribution(waste_type: WasteType = None):
    """
    Create a choropleth map showing waste distribution across regions.
    If waste_type is provided, shows distribution for that specific type.
    Otherwise, shows total waste across all types.
    """
    state = SimulationState.get_instance()

    if waste_type:
        # Get distribution for specific waste type
        data = state.get_waste_type_distribution(waste_type)
        title = f"Distribution of {waste_type.value} across regions"
    else:
        # Sum up all waste types for each region
        data = {}
        for region in RegionType:
            stats = state.get_regional_waste_stats(region)
            data[region] = sum(stats.values())
        title = "Total waste distribution across regions"

    # Region name mapping
    region_name_map = {
        'pomurska': 'Pomurska',
        'podravska': 'Podravska',
        'koroska': 'Koroška',
        'savinjska': 'Savinjska',
        'zasavska': 'Zasavska',
        'posavska': 'Posavska',
        'jugovzhodna_slovenija': 'Jugovzhodna Slovenija',
        'osrednjeslovenska': 'Osrednjeslovenska',
        'gorenjska': 'Gorenjska',
        'primorskonotranjska': 'Primorsko-notranjska',
        'goriska': 'Goriška',
        'obalno-kraska': 'Obalno-kraška'
    }
    
    # Create DataFrame with region names and waste amounts
    df = pd.DataFrame([
        {"region": region_name_map[region.value], "amount": amount}
        for region, amount in data.items()
    ])

    # Load SR.geojson
    with open("data/SR.geojson", "r", encoding='utf-8') as f:
        slovenia_regions_geo = json.load(f)

    # Create choropleth using plotly express
    fig = px.choropleth(
        data_frame=df,
        geojson=slovenia_regions_geo,
        locations="region",
        featureidkey="properties.SR_UIME",  # Match region names from SR.geojson
        color="amount",
        color_continuous_scale="Viridis",
        title=title,
        labels={"amount": "Amount (m³)"}
    )

    # Update the map layout
    fig.update_geos(
        visible=True,
        showcoastlines=True,
        showland=True,
        fitbounds="locations"
    )

    # Remove default country borders
    fig.update_traces(marker_line_width=0)

    # Improve layout
    fig.update_layout(
        margin={"r":0,"t":30,"l":0,"b":0},
        geo=dict(bgcolor='rgba(0,0,0,0)'),
        paper_bgcolor='rgba(0,0,0,0)',
    )

    return fig


def plot_waste_type_composition(region: RegionType):
    """Create pie chart showing waste type composition for a specific region"""
    state = SimulationState.get_instance()
    stats = state.get_regional_waste_stats(region)

    # Filter out waste types with zero amount (only input waste types)
    non_zero_stats = {
        waste_type.value: amount for waste_type, amount in stats.items() 
        if amount > 0 and waste_type.value not in state.total_products
    }

    fig = go.Figure(
        data=[
            go.Pie(
                labels=list(non_zero_stats.keys()),
                values=list(non_zero_stats.values()),
                hole=0.3,
            )
        ]
    )

    fig.update_layout(
        title=f"Waste Composition in {region.value}",
        annotations=[
            dict(text="Waste Types", x=0.5, y=0.5, font_size=20, showarrow=False)
        ],
    )

    return fig

def plot_products_overview():
    """Create an overview of current products vs targets"""
    state = SimulationState.get_instance()

    products = []
    current_amounts = []
    target_amounts = []

    for product, amount in state.total_products.items():
        products.append(product)
        current_amounts.append(amount)
        target_amounts.append(state.target_demands[product])

    fig = go.Figure(data=[
        go.Bar(name="Current", x=products, y=current_amounts),
        go.Bar(name="Target", x=products, y=target_amounts)
    ])

    fig.update_layout(
        barmode='group',
        title="Products Overview - Current vs Target",
        xaxis_title="Product Type",
        yaxis_title="Amount (m³)",
        legend_title="Status"
    )

    return fig

def plot_waste_type_trends():
    """Create subplots showing waste amounts for each input type"""
    state = SimulationState.get_instance()

    # Filter out output product types
    input_waste_types = [wt for wt in WasteType 
                        if wt.value not in state.total_products]
    
    # Create subplot grid
    rows = (len(input_waste_types) + 1) // 2  # Two columns per row
    fig = make_subplots(
        rows=rows, cols=2, 
        subplot_titles=[wt.value for wt in input_waste_types],
        vertical_spacing=0.1
    )

    # Plot input waste types distribution across regions
    for i, waste_type in enumerate(input_waste_types):
        row = (i // 2) + 1
        col = (i % 2) + 1

        data = state.get_waste_type_distribution(waste_type)

        fig.add_trace(
            go.Bar(
                x=[region.value for region in data.keys()],
                y=[amount for amount in data.values()],
                name=waste_type.value,
            ),
            row=row,
            col=col,
        )

    fig.update_layout(
        height=300 * rows,
        width=1000,
        title_text="Regional Distribution by Waste Type",
        showlegend=False,
    )

    return fig

def generate_waste_analysis_report(output_dir: str = "plots"):
    """Generate a comprehensive waste analysis report with multiple visualizations"""
    import os

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate and save overall distribution plot
    total_dist = plot_regional_waste_distribution()
    total_dist.write_html(os.path.join(output_dir, "total_waste_distribution.html"))

    # Generate and save individual waste type distribution plots
    for waste_type in WasteType:
        if waste_type.value not in SimulationState.get_instance().total_products:
            dist_plot = plot_regional_waste_distribution(waste_type)
            dist_plot.write_html(
                os.path.join(output_dir, f"{waste_type.value}_distribution.html")
            )

    # Generate and save regional composition plots
    for region in RegionType:
        comp_plot = plot_waste_type_composition(region)
        comp_plot.write_html(
            os.path.join(output_dir, f"{region.value}_composition.html")
        )

    # Generate and save waste type trends
    trends_plot = plot_waste_type_trends()
    trends_plot.write_html(os.path.join(output_dir, "waste_type_trends.html"))

    # Generate and save products overview
    products_plot = plot_products_overview()
    products_plot.write_html(os.path.join(output_dir, "products_overview.html"))
