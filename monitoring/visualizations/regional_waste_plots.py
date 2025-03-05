import plotly.graph_objects as go
from plotly.subplots import make_subplots
from models.enums import RegionType, WasteType
from models.state import SimulationState


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

    # Create choropleth map
    fig = go.Figure(
        data=go.Choropleth(
            locations=[region.value for region in data.keys()],
            z=[amount for amount in data.values()],
            locationmode="country names",
            colorscale="Viridis",
            colorbar_title="Amount",
        )
    )

    fig.update_layout(
        title=title,
        geo=dict(
            scope="europe",
            center=dict(lat=46.1512, lon=14.9955),  # Center on Slovenia
            projection_scale=20,
        ),
    )

    return fig


def plot_waste_type_composition(region: RegionType):
    """Create a pie chart showing waste type composition for a specific region"""
    state = SimulationState.get_instance()
    stats = state.get_regional_waste_stats(region)

    # Filter out waste types with zero amount
    non_zero_stats = {
        waste_type.value: amount for waste_type, amount in stats.items() if amount > 0
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


def plot_waste_type_trends():
    """Create a subplot with line charts showing waste amounts over time for each type"""
    state = SimulationState.get_instance()

    # Create subplot grid
    waste_types = list(WasteType)
    rows = (len(waste_types) + 1) // 2  # Two columns per row
    fig = make_subplots(
        rows=rows, cols=2, subplot_titles=[wt.value for wt in waste_types]
    )

    # For each waste type, show distribution across regions
    for i, waste_type in enumerate(waste_types):
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
