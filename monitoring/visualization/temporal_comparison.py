import os
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
    os.makedirs(temp_dir, exist_ok=True)
    
    _create_generation_comparison(results, os.path.join(temp_dir, "generation"))
    _create_collection_comparison(results, os.path.join(temp_dir, "collection"))
    _create_collection_efficiency_comparison(results, os.path.join(temp_dir, "collection"))
    _create_processing_comparison(results, os.path.join(temp_dir, "processing"))
    _create_cost_comparison(results, os.path.join(temp_dir, "cost"))
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

    # Group results by base scenario and inventory policy (similar to storage_visualization.py)
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
    
    # Sort each group by stock_strategy for consistent ordering
    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])

    # Define the three entity types and their configurations
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

    # Create plots for each scenario/policy combination and each entity type
    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        # Generate filename-safe identifier
        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')
        
        for config in entity_configs:
            # Create subplots - one for each stock strategy
            num_strategies = len(results_group)
            
            fig = sp.make_subplots(
                rows=num_strategies, 
                cols=1,
                subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
                vertical_spacing=0.12,  # Increase spacing to prevent x-axis overlap
                specs=[[{"secondary_y": False}] for _ in range(num_strategies)]
            )
            
            max_entities = 0  # Track max entities for consistent y-axis scaling
            
            for subplot_idx, result in enumerate(results_group, 1):
                monitor_data = result['monitor_data']
                history_dict = monitor_data[config['history_key']]
                
                # Get all entities for this specific scenario and entity type
                entity_list = sorted(history_dict.keys())
                entity_positions = {entity: idx for idx, entity in enumerate(entity_list)}
                max_entities = max(max_entities, len(entity_list))
                
                if not entity_list:  # Skip if no entities of this type
                    continue

                for entity_name, data in history_dict.items():
                    if 'status' not in data or not data['status']:
                        continue
                        
                    timestamps = data['timestamps']
                    statuses = data['status']
                    y_position = entity_positions[entity_name]

                    # Create segments for different statuses to get proper coloring
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
                                legendgroup=f"{subplot_idx}_{entity_name}",  # Unique group per subplot
                                showlegend=(subplot_idx == 1),  # Only show legend for first subplot
                                hovertemplate=f"Entity: {entity_name}<br>Status: {get_status_label(seg_status)}<br>Time: %{{x}}<extra></extra>"
                            ),
                            row=subplot_idx, col=1
                        )

            # Update layout for this specific configuration
            title = f"{config['title_prefix']} - {base_scenario}<br>Inventory Policy: {inventory_policy}"
            
            fig.update_layout(
                title=title,
                height=max(400, num_strategies * max(200, max_entities * 25)),  # Scale height appropriately
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