import plotly.graph_objects as go
import plotly.subplots as sp
import numpy as np
from typing import Dict, List
from ..utils.visualization_utils import (
    aggregate_generation_data,
    calculate_average_efficiency,
    calculate_processing_throughput
)

def create_temporal_comparisons(results: List[Dict], output_dir: str):
    """Create time-series comparison plots for key metrics"""
    _create_generation_comparison(results, output_dir)
    _create_collection_comparison(results, output_dir)
    _create_processing_comparison(results, output_dir)
    _create_cost_comparison(results, output_dir)
    _create_overflow_comparison(results, output_dir)

def _create_generation_comparison(results: List[Dict], output_dir: str):
    """Compare waste generation across scenarios over time"""
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
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Total Waste Generation Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Volume (m³)",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/generation_comparison.html")

def _create_collection_comparison(results: List[Dict], output_dir: str):
    """Compare collection efficiency across scenarios"""
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['collection_history']

        avg_efficiency = calculate_average_efficiency(history)
        if avg_efficiency['timestamps']:
            fig.add_trace(go.Scatter(
                x=avg_efficiency['timestamps'],
                y=avg_efficiency['efficiency'],
                mode='lines',
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Collection Efficiency Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Average Efficiency",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/collection_comparison.html")

def _create_processing_comparison(results: List[Dict], output_dir: str):
    """Compare processing throughput across scenarios"""
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['processing_history']

        throughput = calculate_processing_throughput(history)
        if throughput['timestamps']:
            fig.add_trace(go.Scatter(
                x=throughput['timestamps'],
                y=throughput['processed'],
                mode='lines',
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Processing Throughput Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Processed Volume (m³)",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/processing_comparison.html")

def _create_cost_comparison(results: List[Dict], output_dir: str):
    """Compare total costs across scenarios"""
    fig = go.Figure()
    
    for result in results:
        monitor_data = result['monitor_data']
        cost_history = monitor_data['cost_history']

        if cost_history['timestamps']:
            total_costs = []
            for i, _ in enumerate(cost_history['timestamps']):
                total_cost = 0
                if i < len(cost_history['energy']):
                    total_cost += cost_history['energy'][i]
                if i < len(cost_history['processing']):
                    total_cost += cost_history['processing'][i]
                if i < len(cost_history['transport']):
                    total_cost += cost_history['transport'][i]
                total_costs.append(total_cost)
            
            fig.add_trace(go.Scatter(
                x=cost_history['timestamps'],
                y=np.cumsum(total_costs),
                mode='lines',
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Cumulative Costs Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Cost",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/cost_comparison.html")

def _create_overflow_comparison(results: List[Dict], output_dir: str):
    """Compare overflow events across scenarios using DecisionTracker data"""
    fig = sp.make_subplots(
        rows=2, cols=2,
        subplot_titles=['Generator Overflow', 'Collector Overflow',
                      'Treatment Overflow', 'Total Overflow Cost'],
        vertical_spacing=0.1
    )
   
    overflow_types = [
        ('generator', 1, 1),
        ('collector', 1, 2), 
        ('treatment', 2, 1),
        ('total_cost', 2, 2)
    ]
   
    for result in results:
        monitor_data = result['monitor_data']
        label = f"{result['inventory_policy']} | {result['stock_strategy']}"

        # lets see how monitor_data is structured
        if isinstance(monitor_data, dict) and 'waste_monitor' in monitor_data:
            monitor_data = monitor_data['waste_monitor']
        elif hasattr(monitor_data, 'get_overflow_statistics'):
            monitor_data = monitor_data.get_overflow_statistics()
        else:
            print(f"Warning: No overflow data available for {label}")
            continue
        
        # Get overflow data from DecisionTracker via WasteMonitor
        overflow_stats = monitor_data['waste_monitor'].get_overflow_statistics()
        
        # Process timeline data for visualization
        timeline_data = _process_overflow_timeline(overflow_stats)
        
        for overflow_type, row, col in overflow_types:
            if overflow_type == 'total_cost':
                # Handle total cost separately
                if 'strategy_costs' in overflow_stats:
                    costs = overflow_stats['strategy_costs']
                    total_cost = costs.get('landfill_penalties', 0) + costs.get('storage_expansion', 0)
                    # For timeline, you might want to track cumulative cost over time
                    fig.add_trace(
                        go.Bar(
                            x=[label],
                            y=[total_cost],
                            name=label,
                            showlegend=False
                        ),
                        row=row, col=col
                    )
            else:
                # Handle facility-specific overflow
                facility_data = timeline_data.get(f'{overflow_type}_overflow', {'timestamps': [], 'values': []})
                if facility_data['timestamps']:
                    fig.add_trace(
                        go.Scatter(
                            x=facility_data['timestamps'],
                            y=facility_data['values'],
                            mode='lines',
                            name=label,
                            showlegend=(row == 1 and col == 1),
                            line={'width': 2}
                        ),
                        row=row, col=col
                    )
   
    fig.update_layout(
        title="Overflow Events Comparison Across Scenarios",
        height=600
    )
   
    fig.write_html(f"{output_dir}/overflow_comparison.html")
           
def _process_overflow_timeline(overflow_stats: Dict) -> Dict:
    """Convert DecisionTracker overflow data to timeline format for visualization"""
    timeline_data = {
        'generator_overflow': {'timestamps': [], 'values': []},
        'collector_overflow': {'timestamps': [], 'values': []},
        'treatment_overflow': {'timestamps': [], 'values': []}
    }
    
    if 'overflow_timeline' in overflow_stats:
        events = overflow_stats['overflow_timeline']
        
        # Group events by facility type
        for event in events:
            facility_type = event.get('facility_type', 'generator')
            overflow_key = f'{facility_type}_overflow'
            
            if overflow_key in timeline_data:
                timeline_data[overflow_key]['timestamps'].append(event.get('timestamp', 0))
                timeline_data[overflow_key]['values'].append(event.get('volume', 0))
    
    return timeline_data