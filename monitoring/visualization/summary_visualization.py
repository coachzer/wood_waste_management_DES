import plotly.graph_objects as go
import plotly.subplots as sp
import pandas as pd
import numpy as np
from typing import Dict, List
from ..utils.visualization_utils import find_pareto_front

def create_cost_impact_comparison(results: List[Dict], output_dir: str):
    """Create bar charts comparing cost and environmental impact breakdowns"""
    cost_components = ['energy', 'processing', 'transport', 'overflow']
    impact_components = ['emissions', 'resource_use']  
    scenario_labels = []
    cost_data = {comp: [] for comp in cost_components}
    impact_data = {comp: [] for comp in impact_components}

    for result in results:
        monitor_data = result['monitor_data']
        scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
        cost_history = monitor_data['cost_history']
        overflow_history = monitor_data['overflow_history']

        # Extract final values for each cost component
        cost_data['energy'].append(np.sum(cost_history.get('energy', [])))
        cost_data['processing'].append(np.sum(cost_history.get('processing', [])))
        cost_data['transport'].append(np.sum(cost_history.get('transport', [])))
        cost_data['overflow'].append(overflow_history.get('total_cost', {}).get('values', [0])[-1] if overflow_history.get('total_cost', {}).get('values') else 0)

    # Bar chart for cost breakdown
    fig_cost = go.Figure()
    for comp in cost_components:
        fig_cost.add_trace(go.Bar(
            x=scenario_labels, 
            y=cost_data[comp], 
            name=comp.title()
        ))
    fig_cost.update_layout(
        title="Cost Breakdown by Scenario", 
        barmode='stack', 
        xaxis_title="Scenario", 
        yaxis_title="Total Cost"
    )
    fig_cost.write_html(f"{output_dir}/cost_breakdown_comparison.html")

def create_pareto_front_plot(results: List[Dict], output_dir: str):
    """Create a 2D scatter plot of cost vs. environmental impact"""
    scenario_labels = []
    total_costs = []
    total_impacts = []

    for result in results:
        monitor_data = result['monitor_data']
        scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
        cost_history = monitor_data['cost_history']
        overflow_history = monitor_data['overflow_history']
        total_cost = np.sum(cost_history.get('energy', [])) + np.sum(cost_history.get('processing', [])) + np.sum(cost_history.get('transport', []))
        total_cost += overflow_history.get('total_cost', {}).get('values', [0])[-1] if overflow_history.get('total_cost', {}).get('values') else 0
        total_impact = getattr(monitor_data['waste_monitor'], 'total_emissions', 0)
        total_costs.append(total_cost)
        total_impacts.append(total_impact)

    # Pareto front calculation
    points = np.array(list(zip(total_costs, total_impacts)))
    pareto_mask = find_pareto_front(points)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=total_costs,
        y=total_impacts,
        mode='markers+text',
        text=scenario_labels,
        textposition='top center',
        marker={"size": 12, "color": ['red' if is_pareto else 'gray' for is_pareto in pareto_mask]},
        name='Scenarios'
    ))
    fig.update_layout(
        title="Scenario Pareto Front: Cost vs. Environmental Impact", 
        xaxis_title="Total Cost", 
        yaxis_title="Total Environmental Impact"
    )
    fig.write_html(f"{output_dir}/pareto_front.html")

def create_summary_dashboard(results: List[Dict], output_dir: str):
    """Create a comprehensive dashboard with key metrics"""
    metrics_data = []
    
    for result in results:
        monitor_data = result['monitor_data']
        generation_history = monitor_data['generation_history']
        collection_history = monitor_data['collection_history']
        processing_history = monitor_data['processing_history']
        overflow_history = monitor_data['overflow_history']

        # Calculate totals
        total_generated = _get_total_generated(generation_history)
        total_collected = sum(_get_total_collected(collection_history).values())
        total_processed = _get_total_processed(processing_history)

        # Calculate overflow cost
        total_overflow_cost = 0
        if 'total_cost' in overflow_history and 'values' in overflow_history['total_cost']:
            cost_values = overflow_history['total_cost']['values']
            if cost_values:
                total_overflow_cost = cost_values[-1]

        # Calculate efficiency percentages
        collection_eff = (total_collected / total_generated * 100) if total_generated > 0 else 0
        processing_eff = (total_processed / total_collected * 100) if total_collected > 0 else 0

        metrics_data.append({
            'Scenario': f"{result['inventory_policy']} | {result['stock_strategy']}",
            'Total Generated': total_generated,
            'Total Collected': total_collected,
            'Total Processed': total_processed,
            'Collection Efficiency': collection_eff,
            'Processing Efficiency': processing_eff,
            'Overflow Cost': total_overflow_cost
        })

    # Create the dashboard visualization
    df = pd.DataFrame(metrics_data)
    fig = sp.make_subplots(
        rows=2, cols=3,
        subplot_titles=['Total Generated (m³)', 'Total Collected (m³)', 'Total Processed (m³)',
                        'Collection Efficiency (%)', 'Processing Efficiency (%)', 'Overflow Cost'],
        vertical_spacing=0.15,
        horizontal_spacing=0.1
    )

    metrics = [
        ('Total Generated', 1, 1),
        ('Total Collected', 1, 2),
        ('Total Processed', 1, 3),
        ('Collection Efficiency', 2, 1),
        ('Processing Efficiency', 2, 2),
        ('Overflow Cost', 2, 3)
    ]

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

    for i, (metric, row, col) in enumerate(metrics):
        fig.add_trace(
            go.Bar(
                x=df['Scenario'],
                y=df[metric],
                name=metric,
                showlegend=False,
                marker_color=colors[i % len(colors)],
                text=[f'{val:.1f}' for val in df[metric]],
                textposition='auto'
            ),
            row=row, col=col
        )

    fig.update_layout(
        title="Scenario Comparison Dashboard - Key Performance Metrics",
        height=800,
        showlegend=False
    )

    # Rotate x-axis labels for better readability
    for i in range(1, 7):
        fig.update_xaxes(tickangle=45, row=(i-1)//3 + 1, col=(i-1)%3 + 1)

    # Save the plots
    fig.write_html(f"{output_dir}/summary_dashboard.html")
    
    # Save metrics summary table
    df.to_html(f"{output_dir}/metrics_summary.html", index=False, 
            table_id="metrics-table", classes="table table-striped table-hover")

def _get_total_generated(history: Dict) -> float:
    """Calculate total waste generated"""
    total = 0
    for data in history.values():
        total_generated = data.get('total_generated', {})
        if isinstance(total_generated, dict):
            for _, values in total_generated.items():
                if isinstance(values, list) and values:
                    total += values[-1]
                elif isinstance(values, (int, float)):
                    total += values
    return total

def _get_total_collected(history: Dict) -> Dict:
    """Calculate collector volumes"""
    collector_volumes = {}
    for collector, data in history.items():
        total = 0
        for _, volumes in data.get("collected_volumes", {}).items():
            if volumes:
                total += volumes[-1] if isinstance(volumes, list) else volumes
        collector_volumes[collector] = total
    return collector_volumes

def _get_total_processed(history: Dict) -> float:
    """Calculate total waste processed"""
    total = 0
    for data in history.values():
        processed = data.get('processed', {})
        if isinstance(processed, dict):
            total_processed = processed.get('total', [])
            if isinstance(total_processed, list) and total_processed:
                total += total_processed[-1]
            elif isinstance(total_processed, (int, float)):
                total += total_processed
    return total
