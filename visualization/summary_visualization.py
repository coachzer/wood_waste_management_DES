import plotly.graph_objects as go
import plotly.subplots as sp
import pandas as pd
import numpy as np
from typing import Dict, List
from config.constants import CHART_PALETTE, DASHBOARD_HEIGHT_PX
from .visualization_utils import last_cumulative_by_entity

def create_cost_impact_comparison(results: List[Dict], output_dir: str):
    """Create bar charts comparing cost and environmental impact breakdowns"""
    cost_components = ['energy_costs', 'operational_costs', 'transport_costs', 'overflow']
    scenario_labels = []
    cost_data = {comp: [] for comp in cost_components}

    for result in results:
        monitor_data = result['monitor_data']
        scenario_labels.append(f"{result['inventory_policy']} | {result['stock_strategy']}")
        
        total_energy = 0
        total_operational = 0
        total_transport = 0
        
        for entity_data in monitor_data.get('generation_history', {}).values():
            if entity_data.get('energy_costs'):
                total_energy += sum(entity_data['energy_costs'])
            if entity_data.get('operational_costs'):
                total_operational += sum(entity_data['operational_costs'])
        
        for entity_data in monitor_data.get('collection_history', {}).values():
            if entity_data.get('energy_costs'):
                total_energy += sum(entity_data['energy_costs'])
            if entity_data.get('operational_costs'):
                total_operational += sum(entity_data['operational_costs'])
            if entity_data.get('transport_costs'):
                total_transport += sum(entity_data['transport_costs'])

        for entity_data in monitor_data.get('processing_history', {}).values():
            operational = entity_data.get('operational', {})
            if operational.get('energy_costs'):
                total_energy += sum(operational['energy_costs'])
            if operational.get('processing_costs'):
                total_operational += sum(operational['processing_costs'])
        
        cost_data['energy_costs'].append(total_energy)
        cost_data['operational_costs'].append(total_operational)
        cost_data['transport_costs'].append(total_transport)
        
        event_history = monitor_data.get('event_history', {})
        overflow_cost = 0
        if 'system_events' in event_history:
            total_costs = event_history['system_events'].get('total_costs', [])
            if total_costs:
                overflow_cost = sum(total_costs)
        cost_data['overflow'].append(overflow_cost)

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

def create_summary_dashboard(results: List[Dict], output_dir: str):
    """Create a comprehensive dashboard with key metrics"""
    metrics_data = []
    
    for result in results:
        monitor_data = result['monitor_data']
        generation_history = monitor_data['generation_history']
        collection_history = monitor_data['collection_history']
        processing_history = monitor_data['processing_history']
        event_history = monitor_data['event_history']

        total_generated = sum(last_cumulative_by_entity(generation_history, 'total_generated').values())
        total_collected = sum(last_cumulative_by_entity(collection_history, 'collected_volumes').values())
        total_processed = sum(last_cumulative_by_entity(processing_history, 'processed.total').values())

        # Calculate event cost (per-event increments, summed to match
        # create_cost_impact_comparison's 'overflow' total)
        total_overflow_cost = 0
        total_costs = event_history.get('system_events', {}).get('total_costs', [])
        if total_costs:
            total_overflow_cost = sum(total_costs)

        collection_eff = (total_collected / total_generated * 100) if total_generated > 0 else 0
        processing_eff = (total_processed / total_collected * 100) if total_collected > 0 else 0

        metrics_data.append({
            'Scenario': f"{result['inventory_policy']} | {result['stock_strategy']}",
            'Total Generated': total_generated,
            'Total Collected': total_collected,
            'Total Processed': total_processed,
            'Collection Efficiency': collection_eff,
            'Processing Efficiency': processing_eff,
            'Event Cost': total_overflow_cost
        })

    df = pd.DataFrame(metrics_data)
    fig = sp.make_subplots(
        rows=2, cols=3,
        subplot_titles=['Total Generated (m³)', 'Total Collected (m³)', 'Total Processed (m³)',
                        'Collection Efficiency (%)', 'Processing Efficiency (%)', 'Event Cost'],
        vertical_spacing=0.15,
        horizontal_spacing=0.1
    )

    metrics = [
        ('Total Generated', 1, 1),
        ('Total Collected', 1, 2),
        ('Total Processed', 1, 3),
        ('Collection Efficiency', 2, 1),
        ('Processing Efficiency', 2, 2),
        ('Event Cost', 2, 3)
    ]

    colors = CHART_PALETTE

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
        height=DASHBOARD_HEIGHT_PX,
        showlegend=False
    )

    for i in range(1, 7):
        fig.update_xaxes(tickangle=45, row=(i-1)//3 + 1, col=(i-1)%3 + 1)

    fig.write_html(f"{output_dir}/summary_dashboard.html")
    
    df.to_html(f"{output_dir}/metrics_summary.html", index=False, 
            table_id="metrics-table", classes="table table-striped table-hover")

