import plotly.graph_objects as go
import plotly.subplots as sp
import os
from typing import Dict, List
from .visualization_utils import (
    extract_storage_data,
    extract_collection_storage_data,
    extract_processor_waste_storage_data,
    extract_processor_finished_goods_storage_data,
    safe_write_image,
)

def create_storage_heatmaps(results: List[Dict], output_dir: str):
    """Create heatmap visualizations of storage utilization over time grouped by scenario and inventory policy"""
    storage_dir = os.path.join(output_dir, "storage_heatmaps")
    os.makedirs(storage_dir, exist_ok=True)

    entity_dir = os.path.join(storage_dir, "entity_storage")
    processing_dir = os.path.join(storage_dir, "processing_storage")
    
    if not results:
        raise ValueError("No results provided to create_storage_heatmaps")
    
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
    
    if not grouped_results:
        raise ValueError("No grouped results created - grouping logic failed")
    
    for key, group in grouped_results.items():
        if not group:
            raise ValueError(f"Empty group found for key {key}")
    
    # Sort each group by stock_strategy for consistent ordering
    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])

    for entity_type in ['generation', 'collection']:
        entity_subdir = os.path.join(entity_dir, entity_type)
        os.makedirs(entity_subdir, exist_ok=True)  # Ensure subdirectory exists
        try:
            _create_entity_storage_heatmaps_grouped(grouped_results, entity_type, entity_subdir)
        except Exception as e:
            raise RuntimeError(f"Failed creating {entity_type} plots: {str(e)}") from e

    # Create processing storage plots
    for storage_type in ['waste', 'finished_goods']:
        processing_subdir = os.path.join(processing_dir, storage_type)
        os.makedirs(processing_subdir, exist_ok=True)  # Ensure subdirectory exists
        try:
            _create_processing_storage_heatmaps_grouped(grouped_results, storage_type, processing_subdir)
        except Exception as e:
            raise RuntimeError(f"Failed creating processing {storage_type} plots: {str(e)}") from e

def _create_processing_storage_heatmaps_grouped(grouped_results: Dict, storage_type: str, output_dir: str):
    """Create grouped heatmaps for each scenario/policy combination for a specific processor storage type"""
    if not grouped_results:
        raise ValueError("Empty grouped_results provided to _create_processing_storage_heatmaps_grouped")

    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        if not results_group:
            raise ValueError(f"Empty results_group for key ({base_scenario}, {inventory_policy})")

        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')

        num_strategies = len(results_group)
        if num_strategies == 0:
            raise ValueError(f"No strategies found for {base_scenario} + {inventory_policy}")

        try:
            fig = sp.make_subplots(
                rows=num_strategies, 
                cols=1,
                subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
                vertical_spacing=0.15
            )
        except Exception as e:
            raise RuntimeError(f"Failed creating subplots for {base_scenario} + {inventory_policy}: {str(e)}") from e

        for i, result in enumerate(results_group, 1):
            if 'monitor_data' not in result:
                raise KeyError(f"Result missing 'monitor_data' key for {base_scenario} + {inventory_policy} + {result['stock_strategy']}")

            monitor_data = result['monitor_data']

            if 'processing_history' not in monitor_data:
                raise KeyError(f"monitor_data missing 'processing_history' key for {base_scenario} + {inventory_policy} + {result['stock_strategy']}")

            history = monitor_data['processing_history']

            match storage_type:
                case "waste":
                    heatmap_data = extract_processor_waste_storage_data(history)
                    title_suffix = "Waste Storage Utilization (%)"
                case 'finished_goods':
                    heatmap_data = extract_processor_finished_goods_storage_data(history)
                    title_suffix = "Finished-Goods Storage Utilization (%)"
                case _:
                    raise ValueError(f"Unknown storage_type: {storage_type}")

            if not heatmap_data:
                raise ValueError(f"No heatmap_data returned for {storage_type} in {base_scenario} + {inventory_policy} + {result['stock_strategy']}")

            if 'z_values' not in heatmap_data:
                raise KeyError(f"heatmap_data missing 'z_values' key for {storage_type}")

            if heatmap_data['z_values']:
                try:
                    fig.add_trace(
                        go.Heatmap(
                            z=heatmap_data['z_values'],
                            x=heatmap_data['x_values'],
                            y=heatmap_data['y_values'],
                            colorscale='RdYlBu_r',
                            zmin=0, zmax=100,
                            showscale=(i == 1),
                            colorbar={"title": title_suffix} if i == 1 else None
                        ),
                        row=i, col=1
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed adding heatmap trace for subplot {i}: {str(e)}") from e

        try:
            fig.update_layout(
                title=f"Processing {title_suffix} - {base_scenario}<br>Inventory Policy: {inventory_policy}",
                height=300 * num_strategies + 100,
                showlegend=False
            )

            for i in range(1, num_strategies + 1):
                fig.update_xaxes(title_text="Time", row=i, col=1)
                fig.update_yaxes(title_text="Processor", row=i, col=1)
        except Exception as e:
            raise RuntimeError(f"Failed updating layout: {str(e)}") from e

        filename = f"processing_{storage_type}_storage_heatmap_{file_id}.html"

        try:
            fig.write_html(f"{output_dir}/{filename}")
        except Exception as e:
            raise RuntimeError(f"Failed writing HTML file {filename}: {str(e)}") from e

        pdf_path = filename.replace(".html", ".pdf")
        safe_write_image(
            fig,
            f"{output_dir}/{pdf_path}",
            height=300 * num_strategies + 100,
            width=1600,
        )

def _create_entity_storage_heatmaps_grouped(grouped_results: Dict, entity_type: str, output_dir: str):
    """Create grouped storage heatmaps for each scenario/policy combination for specific entity type"""

    if not grouped_results:
        raise ValueError("Empty grouped_results provided to _create_entity_storage_heatmaps_grouped")

    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        if not results_group:
            raise ValueError(f"Empty results_group for key ({base_scenario}, {inventory_policy})")

        # Generate filename-safe identifier
        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')

        # Create subplots - one for each stock strategy
        num_strategies = len(results_group)
        if num_strategies == 0:
            raise ValueError(f"No strategies found for {base_scenario} + {inventory_policy}")

        try:
            fig = sp.make_subplots(
                rows=num_strategies, 
                cols=1,
                subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
                vertical_spacing=0.15
            )
        except Exception as e:
            raise RuntimeError(f"Failed creating subplots for {base_scenario} + {inventory_policy}: {str(e)}") from e

        for i, result in enumerate(results_group, 1):

            if 'monitor_data' not in result:
                raise KeyError(f"Result missing 'monitor_data' key for {base_scenario} + {inventory_policy} + {result['stock_strategy']}")

            monitor_data = result['monitor_data']

            if entity_type == 'generation':
                if 'generation_history' not in monitor_data:
                    raise KeyError("monitor_data missing 'generation_history' key")
                history = monitor_data['generation_history']
                heatmap_data = extract_storage_data(history, 'storage_utilization')
            elif entity_type == 'collection':
                if 'collection_history' not in monitor_data:
                    raise KeyError("monitor_data missing 'collection_history' key")
                history = monitor_data['collection_history']
                heatmap_data = extract_collection_storage_data(history)
            else:
                raise ValueError(f"Unknown entity_type: {entity_type}")

            if not heatmap_data:
                raise ValueError(f"No heatmap_data returned for {entity_type}")

            if 'z_values' not in heatmap_data:
                raise KeyError(f"heatmap_data missing 'z_values' key for {entity_type}")

            if heatmap_data['z_values']:
                try:
                    fig.add_trace(
                        go.Heatmap(
                            z=heatmap_data['z_values'],
                            x=heatmap_data['x_values'],
                            y=heatmap_data['y_values'],
                            colorscale='RdYlBu_r',
                            zmin=0, zmax=100,
                            showscale=(i == 1),
                            colorbar={"title": "Storage Utilization (%)"} if i == 1 else None
                        ),
                        row=i, col=1
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed adding heatmap trace for subplot {i}: {str(e)}") from e

        try:
            fig.update_layout(
                title=f"{entity_type.title()} Storage Utilization - {base_scenario}<br>Inventory Policy: {inventory_policy}",
                height=300 * num_strategies + 100,
                showlegend=False
            )

            for i in range(1, num_strategies + 1):
                fig.update_xaxes(title_text="Time", row=i, col=1)
                fig.update_yaxes(title_text="Entity", row=i, col=1)
        except Exception as e:
            raise RuntimeError(f"Failed updating layout: {str(e)}") from e

        filename = f"{entity_type}_storage_heatmap_{file_id}.html"

        try:
            fig.write_html(f"{output_dir}/{filename}")
        except Exception as e:
            raise RuntimeError(f"Failed writing HTML file {filename}: {str(e)}") from e

        pdf_path = filename.replace(".html", ".pdf")
        safe_write_image(
            fig,
            f"{output_dir}/{pdf_path}",
            height=300 * num_strategies + 100,
            width=1600,
        )
