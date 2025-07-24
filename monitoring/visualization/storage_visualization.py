import plotly.graph_objects as go
import plotly.subplots as sp
import os
from typing import Dict, List
from ..utils.visualization_utils import (
    extract_storage_data,
    extract_collection_storage_data,
    extract_processing_storage_data,
    extract_processor_waste_storage_data,
    extract_processor_product_storage_data,
    extract_processor_product_to_sell_storage_data
)

def create_storage_heatmaps(results: List[Dict], output_dir: str):
    """Create heatmap visualizations of storage utilization over time for all scenarios"""
    os.makedirs(output_dir, exist_ok=True)
    
    for entity_type in ['generation', 'collection']:
        _create_entity_storage_heatmaps(results, entity_type, output_dir)

    _create_processing_storage_heatmaps(results, 'waste', output_dir)
    _create_processing_storage_heatmaps(results, 'product', output_dir)
    _create_processing_storage_heatmaps(results, 'product_to_sell', output_dir)

def _create_processing_storage_heatmaps(results: List[Dict], storage_type: str, output_dir: str):
    """Create separate heatmaps for each scenario for a specific processor storage type"""
    for result in results:
        monitor_data = result['monitor_data']
        history = monitor_data['processing_history']
        
        # Generate filename-safe scenario identifier
        scenario_id = f"{result['scenario_name']}_{result['inventory_policy']}_{result['stock_strategy']}"
        scenario_id = scenario_id.replace(' ', '_').replace('|', '_').replace(',', '_')
        
        match storage_type:
            case 'waste':
                heatmap_data = extract_processor_waste_storage_data(history)
                title = "Waste Storage Utilization (%)"
            case 'product':
                heatmap_data = extract_processor_product_storage_data(history)
                title = "Product Storage Utilization (%)"
            case 'product_to_sell':
                heatmap_data = extract_processor_product_to_sell_storage_data(history)
                title = "Product-to-Sell Storage Utilization (%)"

        if heatmap_data['z_values']:
            fig = go.Figure()
            
            fig.add_trace(
                go.Heatmap(
                    z=heatmap_data['z_values'],
                    x=heatmap_data['x_values'],
                    y=heatmap_data['y_values'],
                    colorscale='RdYlBu_r',
                    zmin=0, zmax=100,
                    colorbar={"title": title}
                )
            )
            
            fig.update_layout(
                title=f"Processing {title} - {result['scenario_name']}<br>({result['inventory_policy']}, {result['stock_strategy']})",
                xaxis_title="Time",
                yaxis_title="Processor",
                height=400,
                showlegend=False
            )
            
            filename = f"processing_{storage_type}_storage_heatmap_{scenario_id}.html"
            fig.write_html(f"{output_dir}/{filename}")

def _create_entity_storage_heatmaps(results: List[Dict], entity_type: str, output_dir: str):
    """Create separate storage heatmaps for each scenario for specific entity type"""
    for result in results:
        monitor_data = result['monitor_data']

        # Generate filename-safe scenario identifier
        scenario_id = f"{result['scenario_name']}_{result['inventory_policy']}_{result['stock_strategy']}"
        scenario_id = scenario_id.replace(' ', '_').replace('|', '_').replace(',', '_')
        
        if entity_type == 'generation':
            history = monitor_data['generation_history']
            heatmap_data = extract_storage_data(history, 'storage_utilization')
        elif entity_type == 'collection':
            history = monitor_data['collection_history']    
            heatmap_data = extract_collection_storage_data(history)
        else:  # processing
            history = monitor_data['processing_history']
            heatmap_data = extract_processing_storage_data(history)
        
        if heatmap_data['z_values']:
            fig = go.Figure()
            
            fig.add_trace(
                go.Heatmap(
                    z=heatmap_data['z_values'],
                    x=heatmap_data['x_values'],
                    y=heatmap_data['y_values'],
                    colorscale='RdYlBu_r',
                    zmin=0, zmax=100,
                    colorbar={"title": "Storage Utilization (%)"}
                )
            )
            
            fig.update_layout(
                title=f"{entity_type.title()} Storage Utilization - {result['scenario_name']}<br>({result['inventory_policy']}, {result['stock_strategy']})",
                xaxis_title="Time",
                yaxis_title="Entity",
                height=400,
                showlegend=False
            )
            
            filename = f"{entity_type}_storage_heatmap_{scenario_id}.html"
            fig.write_html(f"{output_dir}/{filename}")
