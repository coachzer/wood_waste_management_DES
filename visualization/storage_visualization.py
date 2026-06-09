import plotly.graph_objects as go
import plotly.subplots as sp
import os
from typing import Dict, List
from config.constants import (
    HEATMAP_COLORSCALE,
    HEATMAP_HEIGHT_PADDING_PX,
    HEATMAP_SUBPLOT_HEIGHT_PX,
    UTILIZATION_PCT_MAX,
    UTILIZATION_PCT_MIN,
    WIDE_EXPORT_WIDTH_PX,
)
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

    # Sort each group by stock_strategy for consistent ordering
    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])

    for entity_type in ['generation', 'collection']:
        entity_subdir = os.path.join(entity_dir, entity_type)
        os.makedirs(entity_subdir, exist_ok=True)
        _create_entity_storage_heatmaps_grouped(grouped_results, entity_type, entity_subdir)

    for storage_type in ['waste', 'finished_goods']:
        processing_subdir = os.path.join(processing_dir, storage_type)
        os.makedirs(processing_subdir, exist_ok=True)
        _create_processing_storage_heatmaps_grouped(grouped_results, storage_type, processing_subdir)

def _create_processing_storage_heatmaps_grouped(grouped_results: Dict, storage_type: str, output_dir: str):
    """Create grouped heatmaps for each scenario/policy combination for a specific processor storage type"""
    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')

        num_strategies = len(results_group)

        fig = sp.make_subplots(
            rows=num_strategies,
            cols=1,
            subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
            vertical_spacing=0.15
        )

        for i, result in enumerate(results_group, 1):
            history = result['monitor_data']['processing_history']

            match storage_type:
                case "waste":
                    heatmap_data = extract_processor_waste_storage_data(history)
                    title_suffix = "Waste Storage Utilization (%)"
                case 'finished_goods':
                    heatmap_data = extract_processor_finished_goods_storage_data(history)
                    title_suffix = "Finished-Goods Storage Utilization (%)"
                case _:
                    raise ValueError(f"Unknown storage_type: {storage_type}")

            if heatmap_data['z_values']:
                fig.add_trace(
                    go.Heatmap(
                        z=heatmap_data['z_values'],
                        x=heatmap_data['x_values'],
                        y=heatmap_data['y_values'],
                        colorscale=HEATMAP_COLORSCALE,
                        zmin=UTILIZATION_PCT_MIN, zmax=UTILIZATION_PCT_MAX,
                        showscale=(i == 1),
                        colorbar={"title": title_suffix} if i == 1 else None
                    ),
                    row=i, col=1
                )

        fig.update_layout(
            title=f"Processing {title_suffix} - {base_scenario}<br>Inventory Policy: {inventory_policy}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            showlegend=False
        )

        for i in range(1, num_strategies + 1):
            fig.update_xaxes(title_text="Time", row=i, col=1)
            fig.update_yaxes(title_text="Processor", row=i, col=1)

        filename = f"processing_{storage_type}_storage_heatmap_{file_id}.html"
        fig.write_html(f"{output_dir}/{filename}")

        pdf_path = filename.replace(".html", ".pdf")
        safe_write_image(
            fig,
            f"{output_dir}/{pdf_path}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            width=WIDE_EXPORT_WIDTH_PX,
        )

def _create_entity_storage_heatmaps_grouped(grouped_results: Dict, entity_type: str, output_dir: str):
    """Create grouped storage heatmaps for each scenario/policy combination for specific entity type"""
    for (base_scenario, inventory_policy), results_group in grouped_results.items():
        # Generate filename-safe identifier
        file_id = f"{base_scenario}_{inventory_policy}"
        file_id = file_id.replace(' ', '_').replace('|', '_').replace(',', '_')

        # Create subplots - one for each stock strategy
        num_strategies = len(results_group)

        fig = sp.make_subplots(
            rows=num_strategies,
            cols=1,
            subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
            vertical_spacing=0.15
        )

        for i, result in enumerate(results_group, 1):
            monitor_data = result['monitor_data']

            if entity_type == 'generation':
                history = monitor_data['generation_history']
                heatmap_data = extract_storage_data(history, 'storage_utilization')
            elif entity_type == 'collection':
                history = monitor_data['collection_history']
                heatmap_data = extract_collection_storage_data(history)
            else:
                raise ValueError(f"Unknown entity_type: {entity_type}")

            if heatmap_data['z_values']:
                fig.add_trace(
                    go.Heatmap(
                        z=heatmap_data['z_values'],
                        x=heatmap_data['x_values'],
                        y=heatmap_data['y_values'],
                        colorscale=HEATMAP_COLORSCALE,
                        zmin=UTILIZATION_PCT_MIN, zmax=UTILIZATION_PCT_MAX,
                        showscale=(i == 1),
                        colorbar={"title": "Storage Utilization (%)"} if i == 1 else None
                    ),
                    row=i, col=1
                )

        fig.update_layout(
            title=f"{entity_type.title()} Storage Utilization - {base_scenario}<br>Inventory Policy: {inventory_policy}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            showlegend=False
        )

        for i in range(1, num_strategies + 1):
            fig.update_xaxes(title_text="Time", row=i, col=1)
            fig.update_yaxes(title_text="Entity", row=i, col=1)

        filename = f"{entity_type}_storage_heatmap_{file_id}.html"
        fig.write_html(f"{output_dir}/{filename}")

        pdf_path = filename.replace(".html", ".pdf")
        safe_write_image(
            fig,
            f"{output_dir}/{pdf_path}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            width=WIDE_EXPORT_WIDTH_PX,
        )
