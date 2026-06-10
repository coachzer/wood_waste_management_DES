import plotly.graph_objects as go
import plotly.subplots as sp
import os
from typing import Callable, Dict, List
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
    extract_processor_waste_storage_data,
    extract_processor_finished_goods_storage_data,
    group_results_by_scenario_and_policy,
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

    grouped_results = group_results_by_scenario_and_policy(results)

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
    match storage_type:
        case "waste":
            extractor = extract_processor_waste_storage_data
            title_suffix = "Waste Storage Utilization (%)"
        case 'finished_goods':
            extractor = extract_processor_finished_goods_storage_data
            title_suffix = "Finished-Goods Storage Utilization (%)"
        case _:
            raise ValueError(f"Unknown storage_type: {storage_type}")

    _create_grouped_storage_heatmaps(
        grouped_results,
        extract_heatmap_data=lambda monitor_data: extractor(monitor_data['processing_history']),
        title_prefix=f"Processing {title_suffix}",
        colorbar_title=title_suffix,
        y_axis_title="Processor",
        filename_prefix=f"processing_{storage_type}_storage_heatmap",
        output_dir=output_dir,
    )

def _create_entity_storage_heatmaps_grouped(grouped_results: Dict, entity_type: str, output_dir: str):
    """Create grouped storage heatmaps for each scenario/policy combination for specific entity type"""
    if entity_type == 'generation':
        history_key = 'generation_history'
    elif entity_type == 'collection':
        history_key = 'collection_history'
    else:
        raise ValueError(f"Unknown entity_type: {entity_type}")

    _create_grouped_storage_heatmaps(
        grouped_results,
        extract_heatmap_data=lambda monitor_data: extract_storage_data(monitor_data[history_key], 'storage_utilization'),
        title_prefix=f"{entity_type.title()} Storage Utilization",
        colorbar_title="Storage Utilization (%)",
        y_axis_title="Entity",
        filename_prefix=f"{entity_type}_storage_heatmap",
        output_dir=output_dir,
    )

def _create_grouped_storage_heatmaps(
    grouped_results: Dict,
    extract_heatmap_data: Callable[[Dict], Dict],
    title_prefix: str,
    colorbar_title: str,
    y_axis_title: str,
    filename_prefix: str,
    output_dir: str,
):
    """Create one stacked-by-strategy heatmap figure per scenario/policy combination"""
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
            heatmap_data = extract_heatmap_data(result['monitor_data'])

            if heatmap_data['z_values']:
                fig.add_trace(
                    go.Heatmap(
                        z=heatmap_data['z_values'],
                        x=heatmap_data['x_values'],
                        y=heatmap_data['y_values'],
                        colorscale=HEATMAP_COLORSCALE,
                        zmin=UTILIZATION_PCT_MIN, zmax=UTILIZATION_PCT_MAX,
                        showscale=(i == 1),
                        colorbar={"title": colorbar_title} if i == 1 else None
                    ),
                    row=i, col=1
                )

        fig.update_layout(
            title=f"{title_prefix} - {base_scenario}<br>Inventory Policy: {inventory_policy}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            showlegend=False
        )

        for i in range(1, num_strategies + 1):
            fig.update_xaxes(title_text="Time", row=i, col=1)
            fig.update_yaxes(title_text=y_axis_title, row=i, col=1)

        filename = f"{filename_prefix}_{file_id}.html"
        fig.write_html(f"{output_dir}/{filename}")

        pdf_path = filename.replace(".html", ".pdf")
        safe_write_image(
            fig,
            f"{output_dir}/{pdf_path}",
            height=HEATMAP_SUBPLOT_HEIGHT_PX * num_strategies + HEATMAP_HEIGHT_PADDING_PX,
            width=WIDE_EXPORT_WIDTH_PX,
        )
