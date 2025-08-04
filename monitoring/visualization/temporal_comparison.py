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
    _create_processing_comparison(results, os.path.join(temp_dir, "processing"))
    _create_cost_comparison(results, os.path.join(temp_dir, "cost"))
    _create_environmental_impact_comparison(results, env_dir)
    _create_environmental_breakdown_comparison(results, env_dir)
    _create_cost_vs_environmental_pareto(results, pareto_dir)
    _create_efficiency_frontier_analysis(results, pareto_dir)
    _create_entity_status_view(results, temp_dir)

def _create_generation_comparison(results: List[Dict], output_dir: str):
    """Compare waste generation across scenarios over time"""
    os.makedirs(output_dir, exist_ok=True)  
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['generation_history']

        total_generation = aggregate_generation_data(history)
        if total_generation['timestamps']:
            fig.add_trace(go.Scatter(
                x=total_generation['timestamps'],
                y=total_generation['volumes'],
                mode='lines',
                name=f"{result['scenario_name']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Total Waste Generation Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Volume (m³)",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/generation_comparison.html")

    png_path = "generation_comparison.png"
    fig.write_image(f"{output_dir}/{png_path}", scale=2)
    print(f"PNG version saved to {png_path}")

def _create_collection_comparison(results: List[Dict], output_dir: str):
    """Compare collection volumes across scenarios"""
    os.makedirs(output_dir, exist_ok=True)
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['collection_history']

        aggregated_data = aggregate_collection_data(history)
        if aggregated_data['timestamps']:
            fig.add_trace(go.Scatter(
                x=aggregated_data['timestamps'],
                y=aggregated_data['volumes'],
                mode='lines',
                name=f"{result['scenario_name']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Collection Volumes Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Total Collected Volume",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/collection_comparison.html")

    png_path = "collection_comparison.png"
    fig.write_image(f"{output_dir}/{png_path}", scale=2)
    print(f"PNG version saved to {png_path}")

def _create_collection_efficiency_comparison(results: List[Dict], output_dir: str):
    """Compare collection efficiency across scenarios"""
    os.makedirs(output_dir, exist_ok=True)
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['collection_history']

        efficiency_data = calculate_average_efficiency(history)
        if efficiency_data:
            fig.add_trace(go.Scatter(
                x=efficiency_data['timestamps'],
                y=efficiency_data['efficiency'],
                mode='lines',
                name=f"{result['scenario_name']}",
                line={'width': 2}
            ))  
    fig.update_layout(
        title="Collection Efficiency Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Average Efficiency (%)",
        hovermode='x unified'
    )

    fig.write_html(f"{output_dir}/collection_efficiency_comparison.html")

    png_path = "collection_efficiency_comparison.png"
    fig.write_image(f"{output_dir}/{png_path}", scale=2)
    print(f"PNG version saved to {png_path}")

def _create_processing_comparison(results: List[Dict], output_dir: str):
    """Compare processing throughput across scenarios"""
    os.makedirs(output_dir, exist_ok=True)
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['processing_history']

        throughput = calculate_storage_levels(history)
        if throughput['timestamps']:
            fig.add_trace(go.Scatter(
                x=throughput['timestamps'],
                y=throughput['storage'],
                mode='lines',
                name=f"{result['scenario_name']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Storage Throughput Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Storage Volume (m³)",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/processing_comparison.html")

    png_path = "processing_comparison.png"
    fig.write_image(f"{output_dir}/{png_path}", scale=2)
    print(f"PNG version saved to {png_path}")

def _create_cost_comparison(results: List[Dict], output_dir: str):
    """Compare cumulative costs across scenarios"""
    os.makedirs(output_dir, exist_ok=True)
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        
        # Collect all timestamps and costs from embedded tracking
        all_costs_by_time = {}
        
        # From generation history
        for entity_data in monitor_data.get('generation_history', {}).values():
            timestamps = entity_data.get('timestamps', [])
            total_costs = entity_data.get('total_costs', [])
            for i, timestamp in enumerate(timestamps):
                if i < len(total_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + total_costs[i]
        
        # From collection history  
        for entity_data in monitor_data.get('collection_history', {}).values():
            timestamps = entity_data.get('timestamps', [])
            total_costs = entity_data.get('total_costs', [])
            for i, timestamp in enumerate(timestamps):
                if i < len(total_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + total_costs[i]
        
        # From processing history
        for entity_data in monitor_data.get('processing_history', {}).values():
            timestamps = entity_data.get('timestamps', [])
            operational = entity_data.get('operational', {})
            total_costs = operational.get('total_costs', [])
            for i, timestamp in enumerate(timestamps):
                if i < len(total_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + total_costs[i]
        
        # Sort by timestamp and calculate cumulative
        if all_costs_by_time:
            timestamps = sorted(all_costs_by_time.keys())
            costs = [all_costs_by_time[t] for t in timestamps]
            cumulative_costs = np.cumsum(costs)
            
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=cumulative_costs,
                mode='lines',
                name=f"{result['scenario_name']}",
                line={'width': 2}
            ))

    fig.update_layout(
        title="Cumulative Costs Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Cost",
        hovermode='x unified'
    )
    fig.write_html(f"{output_dir}/cost_comparison.html")

    png_path = "cost_comparison.png"
    fig.write_image(f"{output_dir}/{png_path}", scale=2)
    print(f"PNG version saved to {png_path}")

def _create_environmental_impact_comparison(results: List[Dict], output_dir: str):
    """Compare environmental impacts across scenarios over time"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Create separate plots for different impact categories
    impact_categories = ['carbon_emissions', 'transport_emissions', 'landfill_emissions', 'total_impact']
    
    for category in impact_categories:
        fig = go.Figure()
        
        for result in results:
            monitor_data = result['monitor_data']
            environmental_history = monitor_data.get('environmental_history', {})
            
            # Collect all timestamps and impacts for this category
            all_impacts_by_time = {}
            
            for entity_name, entity_data in environmental_history.items():
                timestamps = entity_data.get('timestamps', [])
                impacts = entity_data.get(category, [])
                
                for i, timestamp in enumerate(timestamps):
                    if i < len(impacts):
                        all_impacts_by_time[timestamp] = all_impacts_by_time.get(timestamp, 0) + impacts[i]
            
            # Sort by timestamp and calculate cumulative
            if all_impacts_by_time:
                timestamps = sorted(all_impacts_by_time.keys())
                impacts = [all_impacts_by_time[t] for t in timestamps]
                cumulative_impacts = np.cumsum(impacts)
                
                fig.add_trace(go.Scatter(
                    x=timestamps,
                    y=cumulative_impacts,
                    mode='lines',
                    name=f"{result['scenario_name']}",
                    line={'width': 2}
                ))
        
        # Update layout based on category
        category_titles = {
            'carbon_emissions': 'Carbon Emissions',
            'transport_emissions': 'Transport Emissions', 
            'landfill_emissions': 'Landfill Emissions',
            'total_impact': 'Total Environmental Impact'
        }
        
        fig.update_layout(
            title=f"Cumulative {category_titles[category]} Over Time - Scenario Comparison",
            xaxis_title="Time",
            yaxis_title="Cumulative Impact (kg CO₂e)",
            hovermode='x unified'
        )
        
        # Save files
        filename = f"environmental_{category}_comparison"
        fig.write_html(f"{output_dir}/{filename}.html")
        fig.write_image(f"{output_dir}/{filename}.png", scale=2)
        print(f"Environmental impact plot saved: {filename}")

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
    fig.write_image(f"{output_dir}/environmental_breakdown_comparison.png", scale=2)
    print("Environmental breakdown comparison saved")

def _create_cost_vs_environmental_pareto(results: List[Dict], output_dir: str):
    """Create Pareto chart showing cost vs environmental impact trade-offs"""
    os.makedirs(output_dir, exist_ok=True)
    
    scenario_data = []
    
    for result in results:
        monitor_data = result['monitor_data']
        scenario_name = f"{result['inventory_policy']} | {result['stock_strategy']}"
        
        # Calculate total costs from embedded tracking
        total_cost = 0
        
        # From generation history
        for entity_data in monitor_data.get('generation_history', {}).values():
            total_costs = entity_data.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        
        # From collection history
        for entity_data in monitor_data.get('collection_history', {}).values():
            total_costs = entity_data.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        
        # From processing history
        for entity_data in monitor_data.get('processing_history', {}).values():
            operational = entity_data.get('operational', {})
            total_costs = operational.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        
        # Add overflow/event costs
        event_history = monitor_data.get('event_history', {})
        if 'system_events' in event_history:
            event_costs = event_history['system_events'].get('total_costs', [])
            if event_costs:
                total_cost += sum(event_costs)
        
        # Calculate total environmental impact
        total_environmental_impact = 0
        environmental_history = monitor_data.get('environmental_history', {})
        
        for entity_data in environmental_history.values():
            total_impacts = entity_data.get('total_impact', [])
            if total_impacts:
                total_environmental_impact += sum(total_impacts)
        
        scenario_data.append({
            'scenario': scenario_name,
            'short_scenario': result['stock_strategy'],  # For cleaner labels
            'inventory_policy': result['inventory_policy'],
            'stock_strategy': result['stock_strategy'],
            'total_cost': total_cost,
            'total_environmental_impact': total_environmental_impact
        })
    
    # Create the main Pareto chart
    fig = go.Figure()
    
    # Color mapping for inventory policies
    colors = {
        'PUSH': '#1f77b4',
        'PULL': '#ff7f0e'
    }
    
    # Shape mapping for stock strategies
    symbols = {
        'ON_DEMAND': 'circle',
        'REORDER_50': 'square',
        'REORDER_90': 'diamond'
    }
    
    for data in scenario_data:
        fig.add_trace(go.Scatter(
            x=[data['total_cost']],
            y=[data['total_environmental_impact']],
            mode='markers+text',
            marker={
                "color": colors.get(data['inventory_policy'], '#2ca02c'),
                "symbol": symbols.get(data['stock_strategy'], 'circle'),
                "size": 15,
                "line": {'width': 2, 'color': 'white'}
            },
            text=[data['short_scenario']],
            textposition='top center',
            name=f"{data['inventory_policy']} - {data['stock_strategy']}",
            hovertemplate=(
                f"<b>{data['scenario']}</b><br>" +
                "Total Cost: €%{x:,.0f}<br>" +
                "Environmental Impact: %{y:,.0f} kg CO₂e<br>" +
                "<extra></extra>"
            )
        ))
    
    sorted_data = sorted(scenario_data, key=lambda x: x['total_cost'])
    pareto_points = []
    min_impact = float('inf')
    
    for point in sorted_data:
        if point['total_environmental_impact'] < min_impact:
            min_impact = point['total_environmental_impact']
            pareto_points.append(point)
    
    if len(pareto_points) > 1:
        pareto_x = [p['total_cost'] for p in pareto_points]
        pareto_y = [p['total_environmental_impact'] for p in pareto_points]
        
        fig.add_trace(go.Scatter(
            x=pareto_x,
            y=pareto_y,
            mode='lines',
            line={'color': 'red', 'width': 3, 'dash': 'dash'},
            name='Pareto Frontier',
            hoverinfo='skip'
        ))
    
    fig.update_layout(
        title="Cost vs Environmental Impact Pareto Analysis<br><sub>Lower-left is better (lower cost, lower impact)</sub>",
        xaxis_title="Total Cost (€)",
        yaxis_title="Total Environmental Impact (kg CO₂e)",
        showlegend=True,
        legend={
            "yanchor": "top",
            "y": 0.99,
            "xanchor": "left",
            "x": 1.02
        },
        width=1000,
        height=700
    )
    
    # Add annotations for best performers
    if scenario_data:
        # Find minimum cost scenario
        min_cost_scenario = min(scenario_data, key=lambda x: x['total_cost'])
        # Find minimum impact scenario  
        min_impact_scenario = min(scenario_data, key=lambda x: x['total_environmental_impact'])
        
        fig.add_annotation(
            x=min_cost_scenario['total_cost'],
            y=min_cost_scenario['total_environmental_impact'],
            text="Lowest Cost",
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="blue",
            ax=20,
            ay=-30
        )
        
        fig.add_annotation(
            x=min_impact_scenario['total_cost'],
            y=min_impact_scenario['total_environmental_impact'],
            text="Lowest Impact",
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="green",
            ax=20,
            ay=30
        )
    
    # Save the plot
    fig.write_html(f"{output_dir}/cost_vs_environmental_pareto.html")
    fig.write_image(f"{output_dir}/cost_vs_environmental_pareto.png", scale=2)
    print("Cost vs Environmental Pareto chart saved")
    
    # Create a summary table
    df = pd.DataFrame(scenario_data)
    df['cost_rank'] = df['total_cost'].rank()
    df['impact_rank'] = df['total_environmental_impact'].rank()
    df['combined_rank'] = df['cost_rank'] + df['impact_rank']  # Simple ranking
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
    """Create detailed efficiency frontier analysis with multiple metrics"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Create subplots for different trade-off analyses
    fig = sp.make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Cost vs Environmental Impact',
            'Cost vs Collection Efficiency', 
            'Environmental Impact vs Processing Efficiency',
            'Cost Efficiency (Cost per m³ processed)'
        ],
        horizontal_spacing=0.1,
        vertical_spacing=0.15
    )
    
    scenario_data = []
    
    # Collect all metrics for each scenario
    for result in results:
        monitor_data = result['monitor_data']
        
        # Calculate total costs (same as above)
        total_cost = 0
        for entity_data in monitor_data.get('generation_history', {}).values():
            total_costs = entity_data.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        for entity_data in monitor_data.get('collection_history', {}).values():
            total_costs = entity_data.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        for entity_data in monitor_data.get('processing_history', {}).values():
            operational = entity_data.get('operational', {})
            total_costs = operational.get('total_costs', [])
            if total_costs:
                total_cost += sum(total_costs)
        
        # Calculate environmental impact
        total_environmental_impact = 0
        for entity_data in monitor_data.get('environmental_history', {}).values():
            total_impacts = entity_data.get('total_impact', [])
            if total_impacts:
                total_environmental_impact += sum(total_impacts)
        
        # Calculate collection efficiency
        total_generated = sum(
            sum(v[-1] if isinstance(v, list) and v else v for v in data.get('total_generated', {}).values())
            if isinstance(data.get('total_generated'), dict)
            else data.get('total_generated', 0)
            for data in monitor_data.get('generation_history', {}).values()
        )
        
        total_collected = sum(
            sum(volumes[-1] if isinstance(volumes, list) and volumes else [volumes] if volumes else [0]
                for volumes in data.get('collected_volumes', {}).values())
            for data in monitor_data.get('collection_history', {}).values()
        )
        
        collection_efficiency = (total_collected / total_generated * 100) if total_generated > 0 else 0
        
        # Calculate processing efficiency  
        total_processed = sum(
            data.get('processed', {}).get('total', [])[-1] if isinstance(data.get('processed', {}).get('total'), list) and data.get('processed', {}).get('total') else 0
            for data in monitor_data.get('processing_history', {}).values()
        )
        
        processing_efficiency = (total_processed / total_collected * 100) if total_collected > 0 else 0
        
        # Cost efficiency
        cost_per_m3 = total_cost / total_processed if total_processed > 0 else float('inf')
        
        scenario_data.append({
            'scenario': f"{result['inventory_policy']} | {result['stock_strategy']}",
            'inventory_policy': result['inventory_policy'],
            'stock_strategy': result['stock_strategy'],
            'total_cost': total_cost,
            'total_environmental_impact': total_environmental_impact,
            'collection_efficiency': collection_efficiency,
            'processing_efficiency': processing_efficiency,
            'cost_per_m3': cost_per_m3,
            'total_processed': total_processed
        })
    
    colors = {'PUSH': '#1f77b4', 'PULL': '#ff7f0e'}
    symbols = {'ON_DEMAND': 'circle', 'REORDER_50': 'square', 'REORDER_90': 'diamond'}
    
    # Plot 1: Cost vs Environmental Impact
    for data in scenario_data:
        fig.add_trace(go.Scatter(
            x=[data['total_cost']],
            y=[data['total_environmental_impact']],
            mode='markers',
            marker={
                "color": colors.get(data['inventory_policy'], '#2ca02c'),
                "symbol": symbols.get(data['stock_strategy'], 'circle'),
                "size": 10
            },
            name=data['scenario'],
            showlegend=False
        ), row=1, col=1)
    
    # Plot 2: Cost vs Collection Efficiency
    for data in scenario_data:
        fig.add_trace(go.Scatter(
            x=[data['total_cost']],
            y=[data['collection_efficiency']],
            mode='markers',
            marker={
                "color": colors.get(data['inventory_policy'], '#2ca02c'),
                "symbol": symbols.get(data['stock_strategy'], 'circle'),
                "size": 10
            },
            showlegend=False
        ), row=1, col=2)
    
    # Plot 3: Environmental Impact vs Processing Efficiency
    for data in scenario_data:
        fig.add_trace(go.Scatter(
            x=[data['total_environmental_impact']],
            y=[data['processing_efficiency']],
            mode='markers',
            marker={
                "color": colors.get(data['inventory_policy'], '#2ca02c'),
                "symbol": symbols.get(data['stock_strategy'], 'circle'),
                "size": 10
            },
            showlegend=False
        ), row=2, col=1)
    
    # Plot 4: Cost Efficiency
    scenario_names = [data['stock_strategy'] for data in scenario_data]
    cost_efficiencies = [data['cost_per_m3'] if data['cost_per_m3'] != float('inf') else 0 for data in scenario_data]
    
    fig.add_trace(go.Bar(
        x=scenario_names,
        y=cost_efficiencies,
        marker_color=[colors.get(data['inventory_policy'], '#2ca02c') for data in scenario_data],
        showlegend=False
    ), row=2, col=2)
    
    # Update axes
    fig.update_xaxes(title_text="Total Cost (€)", row=1, col=1)
    fig.update_yaxes(title_text="Environmental Impact (kg CO₂e)", row=1, col=1)
    
    fig.update_xaxes(title_text="Total Cost (€)", row=1, col=2)
    fig.update_yaxes(title_text="Collection Efficiency (%)", row=1, col=2)
    
    fig.update_xaxes(title_text="Environmental Impact (kg CO₂e)", row=2, col=1)
    fig.update_yaxes(title_text="Processing Efficiency (%)", row=2, col=1)
    
    fig.update_xaxes(title_text="Stock Strategy", row=2, col=2)
    fig.update_yaxes(title_text="Cost per m³ (€/m³)", row=2, col=2)
    
    fig.update_layout(
        title="Multi-Criteria Efficiency Frontier Analysis",
        height=800,
        showlegend=False
    )
    
    fig.write_html(f"{output_dir}/efficiency_frontier_analysis.html")
    fig.write_image(f"{output_dir}/efficiency_frontier_analysis.png", scale=2)
    print("Efficiency frontier analysis saved")

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

            # Save PNG version
            png_path = filename.replace('.html', '.png')
            fig.write_image(f"{entity_status_dir}/{png_path}", scale=2)
            print(f"PNG version saved to {png_path}")