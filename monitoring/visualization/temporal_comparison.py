import os
import pandas as pd
import plotly.graph_objects as go
import plotly.subplots as sp
import numpy as np
from typing import Dict, List
from ..utils.visualization_utils import (
    aggregate_collection_data,
    aggregate_generation_data,
    calculate_average_efficiency,
    calculate_storage_levels
)

def create_temporal_comparisons(results: List[Dict], output_dir: str):
    """Create time-series comparison plots for key metrics"""
    temp_dir = os.path.join(output_dir, "temporal_comparison")
    env_dir = os.path.join(temp_dir, "environmental")
    pareto_dir = os.path.join(temp_dir, "pareto")
    os.makedirs(temp_dir, exist_ok=True)
    
    _create_generation_comparison(results, os.path.join(temp_dir, "generation"))
    _create_collection_comparison(results, os.path.join(temp_dir, "collection"))
    _create_collection_efficiency_comparison(results, os.path.join(temp_dir, "collection"))
    _create_generation_efficiency_comparison(results, os.path.join(temp_dir, "generation"))
    _create_processing_comparison(results, os.path.join(temp_dir, "processing"))
    _create_cost_comparison(results, os.path.join(temp_dir, "cost"))
    _create_environmental_impact_comparison(results, env_dir)
    _create_environmental_breakdown_comparison(results, env_dir)
    _create_cost_vs_environmental_pareto(results, pareto_dir)
    _create_efficiency_frontier_analysis(results, pareto_dir)
    _create_entity_status_view(results, temp_dir)

def create_output_directory(output_dir: str):
    """Create output directory if it doesn't exist"""
    os.makedirs(output_dir, exist_ok=True)

def save_plot_files(fig: go.Figure, output_dir: str, filename: str, print_message: str = None):
    """Save both HTML and PNG versions of a plot"""
    create_output_directory(output_dir)

    fig.write_html(f"{output_dir}/{filename}.html")

    fig.write_image(f"{output_dir}/{filename}.pdf", scale=2)

    if print_message:
        print(print_message)
    else:
        print(f"Plot saved: {filename}")

def extract_total_costs_from_monitor_data(monitor_data: Dict) -> Dict[str, float]:
    """Extract and aggregate total costs from all history sources in monitor data"""
    all_costs_by_time = {}
    
    def process_cost_data(history_dict: Dict, cost_key: str = 'total_costs'):
        for entity_data in history_dict.values():
            timestamps = entity_data.get('timestamps', [])
            if cost_key == 'operational.total_costs':
                operational = entity_data.get('operational', {})
                total_costs = operational.get('total_costs', [])
            else:
                total_costs = entity_data.get(cost_key, [])
            
            for i, timestamp in enumerate(timestamps):
                if i < len(total_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + total_costs[i]
    
    process_cost_data(monitor_data.get('generation_history', {}))
    process_cost_data(monitor_data.get('collection_history', {}))
    process_cost_data(monitor_data.get('processing_history', {}), 'operational.total_costs')
    
    event_history = monitor_data.get('event_history', {})
    if 'system_events' in event_history:
        event_costs = event_history['system_events'].get('total_costs', [])
        if event_costs:
            event_timestamps = event_history['system_events'].get('timestamps', [])
            for i, timestamp in enumerate(event_timestamps):
                if i < len(event_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + event_costs[i]
    
    return all_costs_by_time

def calculate_cumulative_data(data_by_time: Dict[str, float]) -> tuple:
    """Calculate cumulative data from timestamped values"""
    if not data_by_time:
        return [], []
    
    timestamps = sorted(data_by_time.keys())
    values = [data_by_time[t] for t in timestamps]
    cumulative_values = np.cumsum(values)
    
    return timestamps, cumulative_values

def add_scenario_trace(fig: go.Figure, x_data: list, y_data: list, scenario_name: str, **trace_kwargs):
    """Add a trace for a scenario to a plotly figure"""
    default_kwargs = {
        'mode': 'lines',
        'line': {'width': 2},
        'name': scenario_name
    }
    default_kwargs.update(trace_kwargs)
    
    fig.add_trace(go.Scatter(x=x_data, y=y_data, **default_kwargs))

def create_basic_time_series_plot(title: str, x_title: str, y_title: str) -> go.Figure:
    """Create a basic time series plot with standard layout"""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode='x unified'
    )
    return fig

def extract_environmental_impacts_by_category(monitor_data: Dict, category: str) -> Dict[str, float]:
    """Extract environmental impacts for a specific category from monitor data"""
    all_impacts_by_time = {}
    environmental_history = monitor_data.get('environmental_history', {})
    
    for entity_data in environmental_history.values():
        timestamps = entity_data.get('timestamps', [])
        impacts = entity_data.get(category, [])
        
        for i, timestamp in enumerate(timestamps):
            if i < len(impacts):
                all_impacts_by_time[timestamp] = all_impacts_by_time.get(timestamp, 0) + impacts[i]
    
    return all_impacts_by_time

def calculate_total_environmental_impact(monitor_data: Dict) -> float:
    """Calculate total environmental impact across all categories and entities"""
    total_impact = 0
    environmental_history = monitor_data.get('environmental_history', {})
    
    for entity_data in environmental_history.values():
        total_impacts = entity_data.get('total_impact', [])
        if total_impacts:
            total_impact += sum(total_impacts)
    
    return total_impact

def get_scenario_colors_and_symbols():
    """Return standard color and symbol mappings for scenarios"""
    colors = {
        'push': '#1f77b4',  # Blue
        'pull': '#ff7f0e'   # Orange
    }
    
    symbols = {
        'on_demand': 'circle',
        'reorder_50': 'square', 
        'reorder_90': 'diamond'
    }
    
    return colors, symbols

def create_scenario_label(result: Dict) -> str:
    """Create a standardized scenario label from result data"""
    return f"{result['inventory_policy']} | {result['stock_strategy']}"

def group_results_by_scenario_and_policy(results: List[Dict]) -> Dict:
    """Group results by base scenario name and inventory policy"""
    grouped_results = {}
    
    for result in results:
        scenario_name = result['scenario_name']
        
        if '_push_' in scenario_name:
            base_scenario = scenario_name.split('_push_')[0]
        elif '_pull_' in scenario_name:
            base_scenario = scenario_name.split('_pull_')[0]
        else:
            base_scenario = scenario_name
        
        key = (base_scenario, result['inventory_policy'])
        if key not in grouped_results:
            grouped_results[key] = []
        grouped_results[key].append(result)
    
    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])
    
    return grouped_results

def _create_generation_comparison(results: List[Dict], output_dir: str):
    """Compare waste generation across scenarios over time"""
    fig = create_basic_time_series_plot(
        "Total Waste Generation Over Time - Scenario Comparison",
        "Time",
        "Cumulative Volume (m³)"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['generation_history']
        
        total_generation = aggregate_generation_data(history)
        if total_generation['timestamps']:
            add_scenario_trace(
                fig, 
                total_generation['timestamps'],
                total_generation['volumes'], 
                result['scenario_name']
            )
    
    save_plot_files(fig, output_dir, "generation_comparison", "Generation comparison plot saved")

def _create_collection_comparison(results: List[Dict], output_dir: str):
    """Compare collection volumes across scenarios"""
    fig = create_basic_time_series_plot(
        "Collection Volumes Over Time - Scenario Comparison",
        "Time",
        "Total Collected Volume"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['collection_history']
        
        aggregated_data = aggregate_collection_data(history)
        if aggregated_data['timestamps']:
            add_scenario_trace(
                fig,
                aggregated_data['timestamps'],
                aggregated_data['volumes'],
                result['scenario_name']
            )
    
    save_plot_files(fig, output_dir, "collection_comparison", "Collection comparison plot saved")

def _create_collection_efficiency_comparison(results: List[Dict], output_dir: str):
    """Compare collection efficiency across scenarios"""
    fig = create_basic_time_series_plot(
        "Collection Efficiency Over Time - Scenario Comparison",
        "Time",
        "Average Efficiency (%)"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['collection_history']
        
        efficiency_data = calculate_average_efficiency(history)
        if efficiency_data:
            add_scenario_trace(
                fig,
                efficiency_data['timestamps'],
                efficiency_data['efficiency'],
                result['scenario_name']
            )
    
    save_plot_files(fig, output_dir, "collection_efficiency_comparison", "Collection efficiency comparison plot saved")

def _create_generation_efficiency_comparison(results: List[Dict], output_dir: str):
    """Compare generation efficiency across scenarios"""
    fig = create_basic_time_series_plot(
        "Generation Efficiency Over Time - Scenario Comparison",
        "Time",
        "Average Efficiency (%)"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['generation_history']

        efficiency_data = calculate_average_efficiency(history)
        if efficiency_data:
            add_scenario_trace(
                fig,
                efficiency_data['timestamps'],
                efficiency_data['efficiency'],
                result['scenario_name']
            )
    
    save_plot_files(fig, output_dir, "generation_efficiency_comparison", "Generation efficiency comparison plot saved")

def _create_processing_comparison(results: List[Dict], output_dir: str):
    """Compare processing throughput across scenarios"""
    fig = create_basic_time_series_plot(
        "Storage Throughput Over Time - Scenario Comparison",
        "Time",
        "Cumulative Storage Volume (m³)"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['processing_history']
        
        throughput = calculate_storage_levels(history)
        if throughput['timestamps']:
            add_scenario_trace(
                fig,
                throughput['timestamps'],
                throughput['storage'],
                result['scenario_name']
            )
    
    save_plot_files(fig, output_dir, "processing_comparison", "Processing comparison plot saved")

def _create_cost_comparison(results: List[Dict], output_dir: str):
    """Compare cumulative costs across scenarios"""
    fig = create_basic_time_series_plot(
        "Cumulative Costs Over Time - Scenario Comparison",
        "Time", 
        "Cumulative Cost"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        all_costs_by_time = extract_total_costs_from_monitor_data(monitor_data)
        
        if all_costs_by_time:
            timestamps, cumulative_costs = calculate_cumulative_data(all_costs_by_time)
            add_scenario_trace(fig, timestamps, cumulative_costs, result['scenario_name'])
    
    save_plot_files(fig, output_dir, "cost_comparison", "Cost comparison plot saved")

def _create_environmental_impact_comparison(results: List[Dict], output_dir: str):
    """Compare environmental impacts across scenarios over time"""
    create_output_directory(output_dir)
    
    impact_categories = {
        'carbon_emissions': 'Carbon Emissions',
        'transport_emissions': 'Transport Emissions', 
        'landfill_emissions': 'Landfill Emissions',
        'total_impact': 'Total Environmental Impact'
    }
    
    for category, title in impact_categories.items():
        fig = create_basic_time_series_plot(
            f"Cumulative {title} Over Time - Scenario Comparison",
            "Time",
            "Cumulative Impact (kg CO₂e)"
        )
        
        for result in results:
            monitor_data = result['monitor_data']
            all_impacts_by_time = extract_environmental_impacts_by_category(monitor_data, category)
            
            if all_impacts_by_time:
                timestamps, cumulative_impacts = calculate_cumulative_data(all_impacts_by_time)
                add_scenario_trace(fig, timestamps, cumulative_impacts, result['scenario_name'])
        
        filename = f"environmental_{category}_comparison"
        save_plot_files(fig, output_dir, filename, f"Environmental impact plot saved: {filename}")

def _create_environmental_breakdown_comparison(results: List[Dict], output_dir: str):
    """Create stacked bar chart showing environmental impact breakdown by source"""
    os.makedirs(output_dir, exist_ok=True)

    scenario_labels = []
    impact_data = {
        'carbon_emissions': [],
        'transport_emissions': [], 
        'landfill_emissions': []
    }

    for result in results:
        monitor_data = result['monitor_data']
        scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
        environmental_history = monitor_data.get('environmental_history', {})

        # Sum total impacts by category
        totals = {'carbon_emissions': 0, 'transport_emissions': 0, 'landfill_emissions': 0}

        for entity_data in environmental_history.values():
            for category in totals.keys():
                impacts = entity_data.get(category, [])
                if impacts:
                    totals[category] += sum(impacts)

        for category in totals.keys():
            impact_data[category].append(totals[category])

    # Create stacked bar chart
    fig = go.Figure()
    colors = {'carbon_emissions': '#1f77b4', 'transport_emissions': '#ff7f0e', 'landfill_emissions': '#d62728'}

    for category, color in colors.items():
        fig.add_trace(go.Bar(
            x=scenario_labels,
            y=impact_data[category],
            name=category.replace('_', ' ').title(),
            marker_color=color
        ))

    fig.update_layout(
        title="Environmental Impact Breakdown by Scenario",
        barmode='stack',
        xaxis_title="Scenario",
        yaxis_title="Total Impact (kg CO₂e)",
        xaxis={'tickangle': 45}
    )

    fig.write_html(f"{output_dir}/environmental_breakdown_comparison.html")
    fig.write_image(f"{output_dir}/environmental_breakdown_comparison.pdf", scale=2)
    print("Environmental breakdown comparison saved")

def _create_cost_vs_environmental_pareto(results: List[Dict], output_dir: str):
    """Create Pareto chart showing cost vs environmental impact trade-offs"""
    create_output_directory(output_dir)

    scenario_data = _extract_scenario_metrics(results)
    fig = _create_pareto_scatter_plot(scenario_data)
    # _add_pareto_frontier(fig, scenario_data)

    # Save the plot
    save_plot_files(fig, output_dir, "cost_vs_environmental_pareto", "Cost vs Environmental Pareto chart saved")

    # Create and save ranking table
    _create_pareto_ranking_table(scenario_data, output_dir)

def _extract_scenario_metrics(results: List[Dict]) -> List[Dict]:
    """Extract cost and environmental metrics for each scenario"""
    scenario_data = []

    for result in results:
        monitor_data = result['monitor_data']
        scenario_name = create_scenario_label(result)

        # Calculate total costs using our utility function
        all_costs_by_time = extract_total_costs_from_monitor_data(monitor_data)
        total_cost = sum(all_costs_by_time.values()) if all_costs_by_time else 0

        # Calculate total environmental impact using our utility function
        total_environmental_impact = calculate_total_environmental_impact(monitor_data)

        scenario_data.append({
            'scenario': scenario_name,
            'short_scenario': result['stock_strategy'],
            'inventory_policy': result['inventory_policy'],
            'stock_strategy': result['stock_strategy'],
            'total_cost': total_cost,
            'total_environmental_impact': total_environmental_impact
        })

    return scenario_data


def generate_position_dict(strategy_list):
    """Generate positions that cycle through available options to minimize overlap"""
    positions = [
        "top center",
        "bottom center",
        "middle left",
        "middle right",
        "top left",
        "top right",
        "bottom left",
        "bottom right",
    ]

    unique_strategies = sorted(set(strategy_list))

    return {
        strategy: positions[i % len(positions)]
        for i, strategy in enumerate(unique_strategies)
    }


def _create_pareto_scatter_plot(scenario_data: List[Dict]) -> go.Figure:
    """Create the main scatter plot for Pareto analysis"""
    fig = go.Figure()
    colors, symbols = get_scenario_colors_and_symbols()

    all_strategies = [data["stock_strategy"] for data in scenario_data]

    position_dict = generate_position_dict(all_strategies)

    print("Generated position dictionary:")
    for strategy, position in position_dict.items():
        print(f"'{strategy}': '{position}',")

    for data in scenario_data:
        strategy_name = data["stock_strategy"]

        fig.add_trace(
            go.Scatter(
                x=[data["total_cost"]],
                y=[data["total_environmental_impact"]],
                mode="markers+text",
                marker={
                    "color": colors.get(data["inventory_policy"], "#2ca02c"),
                    "symbol": symbols.get(data["stock_strategy"], "circle"),
                    "size": 12,
                    "line": {"width": 1.5, "color": "white"},
                },
                text=[strategy_name.replace("_", " ")],
                textposition=[position_dict[strategy_name]],
                textfont={"size": 8, "color": "black"},
                name=f"{data['inventory_policy']} - {strategy_name.replace('_', ' ')}",
                hovertemplate=(
                    f"<b>{data['scenario']}</b><br>"
                    + "Total Cost: €%{x:,.0f}<br>"
                    + "Environmental Impact: %{y:,.0f} kg CO₂e<br>"
                    + "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        xaxis={
            "title": {"text": "Total Cost (€)", "font": {"size": 14}},
            "showgrid": True,
            "gridcolor": "#E5E5E5",
            "gridwidth": 0.5,
            "zeroline": False,
            "showline": True,
            "linecolor": "black",
            "linewidth": 1,
            "tickfont": {"size": 12},
        },
        yaxis={
            "title": {
                "text": "Total Environmental Impact (kg CO₂e)",
                "font": {"size": 14},
            },
            "showgrid": True,
            "gridcolor": "#E5E5E5",
            "gridwidth": 0.5,
            "zeroline": False,
            "showline": True,
            "linecolor": "black",
            "linewidth": 1,
            "tickfont": {"size": 12},
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        width=800,
        height=600,
        margin={"l": 80, "r": 40, "t": 40, "b": 60},
    )

    return fig
def _add_pareto_frontier(fig: go.Figure, scenario_data: List[Dict]):
    """Add Pareto frontier or highlight extreme points"""

    def is_dominated(point1, point2):
        return (
            point2["total_cost"] <= point1["total_cost"]
            and point2["total_environmental_impact"]
            <= point1["total_environmental_impact"]
            and (
                point2["total_cost"] < point1["total_cost"]
                or point2["total_environmental_impact"]
                < point1["total_environmental_impact"]
            )
        )

    pareto_points = []
    for point in scenario_data:
        if not any(is_dominated(point, other) for other in scenario_data):
            pareto_points.append(point)

    if len(pareto_points) > 1:
        pareto_points_sorted = sorted(pareto_points, key=lambda x: x["total_cost"])
        pareto_x = [p["total_cost"] for p in pareto_points_sorted]
        pareto_y = [p["total_environmental_impact"] for p in pareto_points_sorted]

        fig.add_trace(
            go.Scatter(
                x=pareto_x,
                y=pareto_y,
                mode="lines+markers",
                line={"color": "#D32F2F", "width": 2},
                marker={"color": "#D32F2F", "size": 8},
                name="Pareto Frontier",
                showlegend=True,
                hoverinfo="skip",
            )
        )
    else:
        # Highlight extreme points instead
        min_cost = min(scenario_data, key=lambda x: x["total_cost"])
        min_impact = min(scenario_data, key=lambda x: x["total_environmental_impact"])

        if min_cost != min_impact:
            fig.add_trace(
                go.Scatter(
                    x=[min_cost["total_cost"], min_impact["total_cost"]],
                    y=[
                        min_cost["total_environmental_impact"],
                        min_impact["total_environmental_impact"],
                    ],
                    mode="lines+markers",
                    line={"color": "#D32F2F", "width": 2, "dash": "dot"},
                    marker={"color": "#D32F2F", "size": 8},
                    name="Efficiency Line",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

    print(f"Found {len(pareto_points)} Pareto-efficient points")

def _create_pareto_ranking_table(scenario_data: List[Dict], output_dir: str):
    """Create and save the Pareto ranking table"""
    df = pd.DataFrame(scenario_data)
    df['cost_rank'] = df['total_cost'].rank()
    df['impact_rank'] = df['total_environmental_impact'].rank()
    df['combined_rank'] = df['cost_rank'] + df['impact_rank']
    df = df.sort_values('combined_rank')
    
    # Save ranking table
    df[['scenario', 'total_cost', 'total_environmental_impact', 'cost_rank', 'impact_rank', 'combined_rank']].to_html(
        f"{output_dir}/pareto_ranking_table.html", 
        index=False,
        float_format=lambda x: f'{x:,.0f}',
        table_id="pareto-table", 
        classes="table table-striped table-hover"
    )
    
    print("Pareto ranking table saved")

def _create_efficiency_frontier_analysis(results: List[Dict], output_dir: str):
    """Create efficiency frontier analysis"""
    create_output_directory(output_dir)

    scenario_data = _extract_efficiency_metrics(results)
    fig = _create_efficiency_subplot_figure()
    _add_efficiency_scatter_plots(fig, scenario_data)
    _add_cost_efficiency_bar_chart(fig, scenario_data)

    fig.update_layout(
        height=800,
        width=1000,
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        legend={
            "yanchor": "top",
            "y": 0.98,
            "xanchor": "left",
            "x": 1.02,
            "font": {"size": 10},
            "bordercolor": "#E5E5E5",
            "borderwidth": 1,
        },
        annotations=[
            {
                "text": "Cost vs Environmental Impact",
                "x": 0.225,
                "y": 1,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Cost vs Collection Efficiency",
                "x": 0.775,
                "y": 1,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Environmental Impact vs Processing Efficiency",
                "x": 0.225,
                "y": 0.45,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Cost Efficiency by Strategy",
                "x": 0.775,
                "y": 0.45,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
        ],
    )

    save_plot_files(fig, output_dir, "efficiency_frontier_analysis", "Efficiency frontier analysis saved")

def _extract_efficiency_metrics(results: List[Dict]) -> List[Dict]:
    """Extract all efficiency metrics for each scenario"""
    scenario_data = []
    
    for result in results:
        monitor_data = result['monitor_data']
        
        # Calculate total costs using utility function
        all_costs_by_time = extract_total_costs_from_monitor_data(monitor_data)
        total_cost = sum(all_costs_by_time.values()) if all_costs_by_time else 0
        
        # Calculate environmental impact using utility function
        total_environmental_impact = calculate_total_environmental_impact(monitor_data)
        
        # Calculate collection and processing metrics
        collection_metrics = _calculate_collection_metrics(monitor_data)
        processing_metrics = _calculate_processing_metrics(monitor_data, collection_metrics['total_collected'])
        
        # Cost efficiency
        cost_per_m3 = total_cost / processing_metrics['total_processed'] if processing_metrics['total_processed'] > 0 else float('inf')
        
        scenario_data.append({
            'scenario': create_scenario_label(result),
            'inventory_policy': result['inventory_policy'],
            'stock_strategy': result['stock_strategy'],
            'total_cost': total_cost,
            'total_environmental_impact': total_environmental_impact,
            'collection_efficiency': collection_metrics['collection_efficiency'],
            'processing_efficiency': processing_metrics['processing_efficiency'],
            'cost_per_m3': cost_per_m3,
            'total_processed': processing_metrics['total_processed']
        })
    
    return scenario_data

def _calculate_collection_metrics(monitor_data: Dict) -> Dict:
    """Calculate collection efficiency metrics"""
    # Calculate total generated
    total_generated = 0
    for data in monitor_data.get('generation_history', {}).values():
        total_gen = data.get('total_generated', {})
        if isinstance(total_gen, dict):
            total_generated += sum(
                v[-1] if isinstance(v, list) and v else v 
                for v in total_gen.values()
            )
        else:
            total_generated += total_gen or 0
    
    # Calculate total collected
    total_collected = 0
    for data in monitor_data.get('collection_history', {}).values():
        collected_volumes = data.get('collected_volumes', {})
        for volumes in collected_volumes.values():
            if isinstance(volumes, list) and volumes:
                total_collected += volumes[-1]
            elif volumes:
                total_collected += volumes
    
    collection_efficiency = (total_collected / total_generated * 100) if total_generated > 0 else 0
    
    return {
        'total_generated': total_generated,
        'total_collected': total_collected,
        'collection_efficiency': collection_efficiency
    }

def _calculate_processing_metrics(monitor_data: Dict, total_collected: float) -> Dict:
    """Calculate processing efficiency metrics"""
    total_processed = 0
    for data in monitor_data.get('processing_history', {}).values():
        processed_data = data.get('processed', {}).get('total', [])
        if isinstance(processed_data, list) and processed_data:
            total_processed += processed_data[-1]
    
    processing_efficiency = (total_processed / total_collected * 100) if total_collected > 0 else 0
    
    return {
        'total_processed': total_processed,
        'processing_efficiency': processing_efficiency
    }

def _create_efficiency_subplot_figure():
    """Create subplot structure"""
    return sp.make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Cost vs Environmental Impact",
            "Cost vs Collection Efficiency",
            "Environmental Impact vs Processing Efficiency",
            "Cost Efficiency by Strategy",
        ],
        horizontal_spacing=0.12,
        vertical_spacing=0.18,
        specs=[
            [{"secondary_y": False}, {"secondary_y": False}],
            [{"secondary_y": False}, {"secondary_y": False}],
        ],
    )

def _add_efficiency_scatter_plots(fig, scenario_data: List[Dict]):
    """Add scatter plots with consistent styling"""
    colors, symbols = get_scenario_colors_and_symbols()

    subplot_configs = [
        {'x': 'total_cost', 'y': 'total_environmental_impact', 'row': 1, 'col': 1, 
         'hover': "Cost: €%{x:,.0f}<br>Impact: %{y:,.0f} kg CO₂e"},
        {'x': 'total_cost', 'y': 'collection_efficiency', 'row': 1, 'col': 2,
         'hover': "Cost: €%{x:,.0f}<br>Efficiency: %{y:.1f}%"},
        {'x': 'total_environmental_impact', 'y': 'processing_efficiency', 'row': 2, 'col': 1,
         'hover': "Impact: %{x:,.0f} kg CO₂e<br>Efficiency: %{y:.1f}%"}
    ]

    for i, config in enumerate(subplot_configs):
        for data in scenario_data:
            fig.add_trace(
                go.Scatter(
                    x=[data[config["x"]]],
                    y=[data[config["y"]]],
                    mode="markers",
                    marker={
                        "color": colors.get(data["inventory_policy"], "#2ca02c"),
                        "symbol": symbols.get(data["stock_strategy"], "circle"),
                        "size": 8,
                        "line": {"width": 1, "color": "white"},
                    },
                    name=f"{data['inventory_policy']} - {data['stock_strategy']}",
                    legendgroup=f"{data['inventory_policy']}_{data['stock_strategy']}",
                    showlegend=(i == 0),
                    hovertemplate=f"<b>{data['scenario']}</b><br>{config['hover']}<extra></extra>",
                ),
                row=config["row"],
                col=config["col"],
            )

    _update_all_subplot_styling(fig)


def _update_all_subplot_styling(fig):
    """Apply consistent styling to all subplots"""

    # Common axis styling
    axis_style = {
        "showgrid": True,
        "gridcolor": "#E5E5E5",
        "gridwidth": 0.5,
        "zeroline": False,
        "showline": True,
        "linecolor": "black",
        "linewidth": 1,
        "tickfont": {"size": 10},
    }

    # Update x-axes
    fig.update_xaxes(title_text="Total Cost (€)", row=1, col=1, **axis_style)
    fig.update_xaxes(title_text="Total Cost (€)", row=1, col=2, **axis_style)
    fig.update_xaxes(
        title_text="Environmental Impact (kg CO₂e)", row=2, col=1, **axis_style
    )
    fig.update_xaxes(title_text="Strategy", row=2, col=2, **axis_style, tickangle=45)

    # Update y-axes
    fig.update_yaxes(
        title_text="Environmental Impact<br>(kg CO₂e)", row=1, col=1, **axis_style
    )
    fig.update_yaxes(title_text="Collection Efficiency (%)", row=1, col=2, **axis_style)
    fig.update_yaxes(title_text="Processing Efficiency (%)", row=2, col=1, **axis_style)
    fig.update_yaxes(title_text="Cost per m³ (€/m³)", row=2, col=2, **axis_style)


def _add_cost_efficiency_bar_chart(fig, scenario_data: List[Dict]):
    """Add bar chart"""
    colors, _ = get_scenario_colors_and_symbols()

    sorted_data = sorted(
        scenario_data,
        key=lambda x: x["cost_per_m3"] if x["cost_per_m3"] != float("inf") else 999999,
    )

    scenario_names = [
        data["stock_strategy"].replace("_", " ").title() for data in sorted_data
    ]
    cost_efficiencies = [
        data["cost_per_m3"] if data["cost_per_m3"] != float("inf") else 0
        for data in sorted_data
    ]
    bar_colors = [
        colors.get(data["inventory_policy"], "#2ca02c") for data in sorted_data
    ]

    fig.add_trace(
        go.Bar(
            x=scenario_names,
            y=cost_efficiencies,
            marker={
                "color": bar_colors,
                "line": {"color": "white", "width": 1},
            },
            showlegend=False,
            hovertemplate="<b>%{x}</b><br>Cost per m³: €%{y:,.2f}<extra></extra>",
        ),
        row=2,
        col=2,
    )


def _create_entity_status_view(results: List[Dict], output_dir: str):
    """Create entity status timeline plots grouped by scenario and inventory policy, with stock strategies as subplots."""

    # Create entity_status subdirectory
    entity_status_dir = os.path.join(output_dir, "entity_status")
    os.makedirs(entity_status_dir, exist_ok=True)

    def get_status_color(status):
        color_map = {
            'OPERATIONAL': 'green', 'FAILED': 'red', 'RECOVERING': 'orange',
            1: 'green', 2: 'red', 3: 'orange'
        }
        return color_map.get(status, 'gray')

    def get_status_label(status):
        label_map = {
            'OPERATIONAL': 'OPERATIONAL', 'FAILED': 'FAILED', 'RECOVERING': 'RECOVERING',
            1: 'OPERATIONAL', 2: 'FAILED', 3: 'RECOVERING',
        }
        return label_map.get(status, f'UNKNOWN_{status}')

    grouped_results = {}
    for result in results:
        scenario_name = result['scenario_name']

        # Extract base scenario name
        if '_push_' in scenario_name:
            base_scenario = scenario_name.split('_push_')[0]
        elif '_pull_' in scenario_name:
            base_scenario = scenario_name.split('_pull_')[0]
        else:
            base_scenario = scenario_name

        key = (base_scenario, result['inventory_policy'])
        if key not in grouped_results:
            grouped_results[key] = []
        grouped_results[key].append(result)

    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])

    entity_configs = [
        {
            'history_key': 'generation_history',
            'title_prefix': 'Generator Status Timeline',
            'filename_prefix': 'generator_status_timeline',
            'y_title': 'Generation Entities'
        },
        {
            'history_key': 'collection_history', 
            'title_prefix': 'Collector Status Timeline',
            'filename_prefix': 'collector_status_timeline',
            'y_title': 'Collection Entities'
        },
        {
            'history_key': 'processing_history',
            'title_prefix': 'Treatment Facility Status Timeline', 
            'filename_prefix': 'treatment_status_timeline',
            'y_title': 'Processing Entities'
        }
    ]

    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')

        for config in entity_configs:
            num_strategies = len(results_group)

            fig = sp.make_subplots(
                rows=num_strategies, 
                cols=1,
                subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
                vertical_spacing=0.12,  
                specs=[[{"secondary_y": False}] for _ in range(num_strategies)]
            )

            max_entities = 0  

            for subplot_idx, result in enumerate(results_group, 1):
                monitor_data = result['monitor_data']
                history_dict = monitor_data[config['history_key']]

                entity_list = sorted(history_dict.keys())
                entity_positions = {entity: idx for idx, entity in enumerate(entity_list)}
                max_entities = max(max_entities, len(entity_list))

                if not entity_list:  
                    continue

                for entity_name, data in history_dict.items():
                    if 'status' not in data or not data['status']:
                        continue

                    timestamps = data['timestamps']
                    statuses = data['status']
                    y_position = entity_positions[entity_name]

                    segments = []
                    if timestamps and statuses:
                        current_status = statuses[0]
                        start_idx = 0

                        for idx in range(1, len(statuses)):
                            if statuses[idx] != current_status:
                                segments.append((start_idx, idx, current_status))
                                start_idx = idx
                                current_status = statuses[idx]

                        # Add the final segment
                        segments.append((start_idx, len(statuses), current_status))

                    # Add one trace per segment with proper colors
                    for seg_start, seg_end, seg_status in segments:
                        seg_timestamps = timestamps[seg_start:seg_end]
                        seg_y = [y_position] * len(seg_timestamps)

                        fig.add_trace(
                            go.Scatter(
                                x=seg_timestamps,
                                y=seg_y,
                                mode='lines',
                                line={'color': get_status_color(seg_status), 'width': 4},
                                name=f"{entity_name} - {get_status_label(seg_status)}",
                                legendgroup=f"{subplot_idx}_{entity_name}",
                                showlegend=(subplot_idx == 1),  
                                hovertemplate=f"Entity: {entity_name}<br>Status: {get_status_label(seg_status)}<br>Time: %{{x}}<extra></extra>"
                            ),
                            row=subplot_idx, col=1
                        )

            title = f"{config['title_prefix']} - {base_scenario}<br>Inventory Policy: {inventory_policy}"

            fig.update_layout(
                title=title,
                height=max(400, num_strategies * max(200, max_entities * 25)), 
                showlegend=True,
                legend={
                    'orientation': 'v',
                    'yanchor': 'top',
                    'y': 1,
                    'xanchor': 'left',
                    'x': 1.02
                }
            )

            # Update axes for each subplot
            for i in range(1, num_strategies + 1):
                fig.update_xaxes(title_text="Time", row=i, col=1)
                fig.update_yaxes(title_text=config['y_title'], row=i, col=1)

            # Save individual file with scenario and policy specific naming
            filename = f"{config['filename_prefix']}_{file_id}.html"
            fig.write_html(f"{entity_status_dir}/{filename}")

            # Save PDF version
            pdf_path = filename.replace(".html", ".pdf")
            fig.write_image(f"{entity_status_dir}/{pdf_path}", scale=2)
            print(f"PDF version saved to {pdf_path}")
