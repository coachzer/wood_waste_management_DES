import plotly.graph_objects as go
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
    _create_generation_comparison(results, output_dir)
    _create_collection_comparison(results, output_dir)
    _create_collection_efficiency_comparison(results, output_dir)
    _create_processing_comparison(results, output_dir)
    _create_cost_comparison(results, output_dir)
    _create_entity_status_view(results, output_dir)

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
    """Compare collection volumes across scenarios"""
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
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Collection Volumes Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Total Collected Volume",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/collection_comparison.html")

def _create_collection_efficiency_comparison(results: List[Dict], output_dir: str):
    """Compare collection efficiency across scenarios"""
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
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))  
    fig.update_layout(
        title="Collection Efficiency Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Average Efficiency (%)",
        hovermode='x unified'
    )

    fig.write_html(f"{output_dir}/collection_efficiency_comparison.html")

def _create_processing_comparison(results: List[Dict], output_dir: str):
    """Compare processing throughput across scenarios"""
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
                name=f"{result['inventory_policy']} | {result['stock_strategy']}",
                line={'width': 2}
            ))
    
    fig.update_layout(
        title="Storage Throughput Over Time - Scenario Comparison",
        xaxis_title="Time",
        yaxis_title="Cumulative Storage Volume (m³)",
        hovermode='x unified'
    )
    
    fig.write_html(f"{output_dir}/processing_comparison.html")

def _create_cost_comparison(results: List[Dict], output_dir: str):
    fig = go.Figure()
    for result in results:
        by_cost = result['monitor_data']['cost_history']['by_cost_type']
        timestamps = sorted({t for cost in by_cost.values() for t in cost['timestamps']})
        total_costs = []
        for t in timestamps:
            cost_sum = sum(
                cost['values'][cost['timestamps'].index(t)]
                for cost in by_cost.values()
                if t in cost['timestamps']
            )
            total_costs.append(cost_sum)
        fig.add_trace(go.Scatter(
            x=timestamps,
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


def _create_entity_status_view(results: List[Dict], output_dir: str):
    """Create entity status timeline plots with entities on y-axis and time-based status segments."""
    
    def get_status_color(status):
        """Get color for any status value"""
        color_map = {
            'OPERATIONAL': 'green',
            'FAILED': 'red', 
            'RECOVERING': 'orange',
            1: 'green',    # EntityStatus.OPERATIONAL
            2: 'red',      # EntityStatus.FAILED  
            3: 'orange',   # EntityStatus.RECOVERING
        }
        return color_map.get(status, 'gray')

    def get_status_label(status):
        """Get readable label for status"""
        label_map = {
            'OPERATIONAL': 'OPERATIONAL',
            'FAILED': 'FAILED',
            'RECOVERING': 'RECOVERING',
            1: 'OPERATIONAL',
            2: 'FAILED',
            3: 'RECOVERING',
        }
        return label_map.get(status, f'UNKNOWN_{status}')

    # Define the three entity types and their configurations
    entity_configs = [
        {
            'history_key': 'generation_history',
            'title': 'Generator Status Timeline',
            'filename': 'generator_status_timeline.html',
            'y_title': 'Generation Entities'
        },
        {
            'history_key': 'collection_history', 
            'title': 'Collector Status Timeline',
            'filename': 'collector_status_timeline.html',
            'y_title': 'Collection Entities'
        },
        {
            'history_key': 'processing_history',
            'title': 'Treatment Facility Status Timeline', 
            'filename': 'treatment_status_timeline.html',
            'y_title': 'Processing Entities'
        }
    ]

    # Create a separate plot for each entity type
    for config in entity_configs:
        fig = go.Figure()
        
        # Collect all unique entities for this type
        all_entities = set()
        for result in results:
            monitor_data = result['monitor_data']
            history_dict = monitor_data[config['history_key']]
            for entity_name in history_dict.keys():
                all_entities.add(entity_name)
        
        # Create ordered list and position mapping
        entity_list = sorted(all_entities)
        entity_positions = {entity: idx for idx, entity in enumerate(entity_list)}

        for result in results:
            monitor_data = result['monitor_data']
            label = f"{result['inventory_policy']} | {result['stock_strategy']}"
            history_dict = monitor_data[config['history_key']]

            for entity_name, data in history_dict.items():
                if 'status' not in data or not data['status']:
                    continue
                    
                timestamps = data['timestamps']
                statuses = data['status']
                y_position = entity_positions[entity_name]

                # Identify contiguous segments of identical status
                segments = []
                start_idx = 0
                current_status = statuses[0]

                for idx in range(1, len(statuses)):
                    if statuses[idx] != current_status:
                        segments.append((start_idx, idx, current_status))
                        start_idx = idx
                        current_status = statuses[idx]
                
                segments.append((start_idx, len(statuses), current_status))

                # Add one trace per segment, positioned at entity's y-coordinate
                for seg_start, seg_end, seg_status in segments:
                    seg_ts = timestamps[seg_start:seg_end]
                    seg_y = [y_position] * len(seg_ts)

                    fig.add_trace(
                        go.Scatter(
                            x=seg_ts,
                            y=seg_y,
                            mode='lines',
                            name=f"{label} – {entity_name}",
                            legendgroup=f"{label} – {entity_name}",
                            line={'color': get_status_color(seg_status), 'width': 3},
                            hovertemplate=f"Entity: {entity_name}<br>Status: {get_status_label(seg_status)}<br>Time: %{{x}}<extra></extra>"
                        )
                    )

        # Update layout for this specific entity type
        fig.update_layout(
            title=config['title'],
            height=600,
            xaxis_title="Time",
            yaxis={
                "tickvals": list(range(len(entity_list))),
                "ticktext": entity_list,
                "title": config['y_title']
            }
        )

        # Save individual file
        fig.write_html(f"{output_dir}/{config['filename']}")
