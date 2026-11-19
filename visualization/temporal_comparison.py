import math
import os
import plotly.graph_objects as go
import plotly.subplots as sp
import numpy as np
from typing import Dict, List
from config.constants import FRONTIER_FIGURE_HEIGHT_PX, FRONTIER_FIGURE_WIDTH_PX
from visualization.figure_style import POLICY_COLORS, STRATEGY_SYMBOLS
from instrumentation.history_store import EMISSION_KINDS, total_emissions_kgco2e
from .visualization_utils import (
    aggregate_collection_data,
    aggregate_generation_data,
    calculate_average_efficiency,
    calculate_storage_levels,
    create_scenario_label,
    group_results_by_scenario_and_policy,
    last_cumulative_by_entity,
    save_plot_files,
)

def create_temporal_comparisons(results: List[Dict], output_dir: str):
    """Create time-series comparison plots for key metrics"""
    temp_dir = os.path.join(output_dir, "temporal_comparison")
    env_dir = os.path.join(temp_dir, "environmental")
    pareto_dir = os.path.join(temp_dir, "pareto")
    os.makedirs(temp_dir, exist_ok=True)

    for spec in _METRIC_COMPARISON_SPECS:
        _create_metric_comparison(results, os.path.join(temp_dir, spec['subdir']), spec)
    _create_cost_comparison(results, os.path.join(temp_dir, "cost"))
    _create_environmental_impact_comparison(results, env_dir)
    _create_environmental_breakdown_comparison(results, env_dir)
    _create_efficiency_frontier_analysis(results, pareto_dir)
    _create_entity_status_view(results, temp_dir)

def extract_total_costs_from_monitor_data(monitor_data: Dict) -> Dict[str, float]:
    """Extract and aggregate total costs from all history sources in monitor data

    The cost series are per-tick increments, so summing at the union of
    entity timestamps is alignment-safe: an entity absent at a timestamp
    contributed nothing then. Do NOT route cumulative or level series
    through this pattern -- those need ``aggregate_aligned_series``
    (visualization_utils), or absent entities saw the aggregate downward.
    """
    all_costs_by_time = {}
    
    def process_cost_data(history_dict: Dict, cost_key: str = 'total_costs'):
        for entity_data in history_dict.values():
            timestamps = entity_data.get('timestamps', [])
            if '.' in cost_key:
                parent_key, child_key = cost_key.split('.', 1)
                total_costs = entity_data.get(parent_key, {}).get(child_key, [])
            else:
                total_costs = entity_data.get(cost_key, [])
            
            for i, timestamp in enumerate(timestamps):
                if i < len(total_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + total_costs[i]
    
    process_cost_data(monitor_data.get('generation_history', {}), 'holding_costs')
    process_cost_data(monitor_data.get('collection_history', {}))
    process_cost_data(monitor_data.get('collection_history', {}), 'holding_costs')
    process_cost_data(monitor_data.get('processing_history', {}), 'operational.total_costs')
    process_cost_data(monitor_data.get('processing_history', {}), 'operational.holding_costs')
    
    event_history = monitor_data.get('event_history', {})
    if 'system_events' in event_history:
        event_costs = event_history['system_events'].get('total_costs', [])
        if event_costs:
            event_timestamps = event_history['system_events'].get('timestamps', [])
            for i, timestamp in enumerate(event_timestamps):
                if i < len(event_costs):
                    all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + event_costs[i]

    # Landfill costs come from the per-entity landfill ledger, not the
    # system-event stream (which carries expansions only).
    for entity_data in monitor_data.get('landfill_history', {}).values():
        timestamps = entity_data.get('timestamps', [])
        costs = entity_data.get('costs', [])
        for i, timestamp in enumerate(timestamps):
            if i < len(costs):
                all_costs_by_time[timestamp] = all_costs_by_time.get(timestamp, 0) + costs[i]
    
    return all_costs_by_time

def calculate_cumulative_data(data_by_time: Dict[str, float]) -> tuple:
    """Calculate cumulative data from timestamped values

    Input values must be per-tick increments (cumsum of increments is exact
    regardless of timestamp alignment). Feeding already-cumulative series
    here double-counts them.
    """
    if not data_by_time:
        return [], []
    
    timestamps = sorted(data_by_time.keys())
    values = [data_by_time[t] for t in timestamps]
    cumulative_values = np.cumsum(values)
    
    return timestamps, cumulative_values

def add_scenario_trace(fig: go.Figure, x_data: list, y_data: list, scenario_name: str, **trace_kwargs):
    """Add a trace for a scenario to a plotly figure"""
    default_kwargs = {
        'mode': 'lines',
        'line': {'width': 2},
        'name': scenario_name
    }
    default_kwargs.update(trace_kwargs)
    
    fig.add_trace(go.Scatter(x=x_data, y=y_data, **default_kwargs))

def create_basic_time_series_plot(title: str, x_title: str, y_title: str) -> go.Figure:
    """Create a basic time series plot with standard layout"""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode='x unified'
    )
    return fig

def extract_environmental_impacts_by_category(monitor_data: Dict, category: str) -> Dict[str, float]:
    """Extract environmental impacts for a specific category from monitor data

    Impact series are per-tick increments (alignment-safe to sum at the union
    of timestamps); environmental_history is genuinely misaligned across
    entities, and this increment-sum is the only correct aggregation for it.
    """
    all_impacts_by_time = {}
    environmental_history = monitor_data.get('environmental_history', {})
    
    for entity_data in environmental_history.values():
        timestamps = entity_data.get('timestamps', [])
        impacts = entity_data.get(category, [])
        
        for i, timestamp in enumerate(timestamps):
            if i < len(impacts):
                all_impacts_by_time[timestamp] = all_impacts_by_time.get(timestamp, 0) + impacts[i]
    
    return all_impacts_by_time

_METRIC_COMPARISON_SPECS = [
    {
        'subdir': "generation",
        'history_key': 'generation_history',
        'aggregate': aggregate_generation_data,
        'value_key': 'volumes',
        'title': "Total Waste Generation Over Time - Scenario Comparison",
        'y_title': "Cumulative Volume (m³)",
        'filename': "generation_comparison",
        'message': "Generation comparison plot saved",
    },
    {
        'subdir': "collection",
        'history_key': 'collection_history',
        'aggregate': aggregate_collection_data,
        'value_key': 'volumes',
        'title': "Collection Volumes Over Time - Scenario Comparison",
        'y_title': "Total Collected Volume",
        'filename': "collection_comparison",
        'message': "Collection comparison plot saved",
    },
    {
        'subdir': "collection",
        'history_key': 'collection_history',
        'aggregate': calculate_average_efficiency,
        'value_key': 'efficiency',
        'scale': 100.0,
        'title': "Collection Efficiency Over Time - Scenario Comparison",
        'y_title': "Average Efficiency (%)",
        'filename': "collection_efficiency_comparison",
        'message': "Collection efficiency comparison plot saved",
    },
    {
        'subdir': "generation",
        'history_key': 'generation_history',
        'aggregate': calculate_average_efficiency,
        'value_key': 'efficiency',
        'scale': 100.0,
        'title': "Generation Efficiency Over Time - Scenario Comparison",
        'y_title': "Average Efficiency (%)",
        'filename': "generation_efficiency_comparison",
        'message': "Generation efficiency comparison plot saved",
    },
    {
        'subdir': "processing",
        'history_key': 'processing_history',
        'aggregate': calculate_storage_levels,
        'value_key': 'storage',
        'title': "Treatment Waste Storage Level Over Time - Scenario Comparison",
        'y_title': "Storage Level (m³)",
        'filename': "processing_comparison",
        'message': "Processing comparison plot saved",
    },
]

def _create_metric_comparison(results: List[Dict], output_dir: str, spec: Dict):
    """Compare one aggregated metric across scenarios over time"""
    fig = create_basic_time_series_plot(spec['title'], "Time", spec['y_title'])
    scale = spec.get('scale', 1.0)

    for result in results:
        history = result['monitor_data'][spec['history_key']]
        data = spec['aggregate'](history)
        if data['timestamps']:
            y_values = (
                [val * scale for val in data[spec['value_key']]]
                if scale != 1.0
                else data[spec['value_key']]
            )
            add_scenario_trace(
                fig,
                data['timestamps'],
                y_values,
                result['scenario_name']
            )

    save_plot_files(fig, output_dir, spec['filename'], spec['message'])

def _create_cost_comparison(results: List[Dict], output_dir: str):
    """Compare cumulative costs across scenarios"""
    fig = create_basic_time_series_plot(
        "Cumulative Costs Over Time - Scenario Comparison",
        "Time", 
        "Cumulative Cost"
    )
    
    for result in results:
        monitor_data = result['monitor_data']
        all_costs_by_time = extract_total_costs_from_monitor_data(monitor_data)
        
        if all_costs_by_time:
            timestamps, cumulative_costs = calculate_cumulative_data(all_costs_by_time)
            add_scenario_trace(fig, timestamps, cumulative_costs, result['scenario_name'])
    
    save_plot_files(fig, output_dir, "cost_comparison", "Cost comparison plot saved")

def _create_environmental_impact_comparison(results: List[Dict], output_dir: str):
    """Compare environmental impacts across scenarios over time"""
    os.makedirs(output_dir, exist_ok=True)
    
    impact_categories = {kind: kind.replace('_', ' ').title() for kind in EMISSION_KINDS}
    impact_categories['total_impact'] = 'Total Environmental Impact'
    
    for category, title in impact_categories.items():
        fig = create_basic_time_series_plot(
            f"Cumulative {title} Over Time - Scenario Comparison",
            "Time",
            "Cumulative Impact (kg CO₂e)"
        )
        
        for result in results:
            monitor_data = result['monitor_data']
            all_impacts_by_time = extract_environmental_impacts_by_category(monitor_data, category)
            
            if all_impacts_by_time:
                timestamps, cumulative_impacts = calculate_cumulative_data(all_impacts_by_time)
                add_scenario_trace(fig, timestamps, cumulative_impacts, result['scenario_name'])
        
        filename = f"environmental_{category}_comparison"
        save_plot_files(fig, output_dir, filename, f"Environmental impact plot saved: {filename}")

def _create_environmental_breakdown_comparison(results: List[Dict], output_dir: str):
    """Create stacked bar chart showing environmental impact breakdown by source"""
    os.makedirs(output_dir, exist_ok=True)

    scenario_labels = []
    impact_data = {kind: [] for kind in EMISSION_KINDS}

    for result in results:
        monitor_data = result['monitor_data']
        scenario_labels.append(create_scenario_label(result))
        environmental_history = monitor_data.get('environmental_history', {})

        totals = {kind: 0 for kind in EMISSION_KINDS}

        for entity_data in environmental_history.values():
            for category in EMISSION_KINDS:
                impacts = entity_data.get(category, [])
                if impacts:
                    totals[category] += sum(impacts)

        for category in EMISSION_KINDS:
            impact_data[category].append(totals[category])

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

    save_plot_files(fig, output_dir, "environmental_breakdown_comparison", "Environmental breakdown comparison saved")

def _create_efficiency_frontier_analysis(results: List[Dict], output_dir: str):
    """Create efficiency frontier analysis"""
    os.makedirs(output_dir, exist_ok=True)

    scenario_data = _extract_efficiency_metrics(results)
    fig = _create_efficiency_subplot_figure()
    _add_efficiency_scatter_plots(fig, scenario_data)
    _add_cost_efficiency_bar_chart(fig, scenario_data)

    fig.update_layout(
        height=FRONTIER_FIGURE_HEIGHT_PX,
        width=FRONTIER_FIGURE_WIDTH_PX,
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=True,
        legend={
            "yanchor": "top",
            "y": 0.98,
            "xanchor": "left",
            "x": 1.02,
            "font": {"size": 10},
            "bordercolor": "#E5E5E5",
            "borderwidth": 1,
        },
        annotations=[
            {
                "text": "Cost vs Environmental Impact",
                "x": 0.225,
                "y": 1,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Cost vs Collection Efficiency",
                "x": 0.775,
                "y": 1,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Environmental Impact vs Processing Efficiency",
                "x": 0.225,
                "y": 0.45,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
            {
                "text": "Cost Efficiency by Strategy",
                "x": 0.775,
                "y": 0.45,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12},
            },
        ],
    )

    save_plot_files(fig, output_dir, "efficiency_frontier_analysis", "Efficiency frontier analysis saved")

def _extract_efficiency_metrics(results: List[Dict]) -> List[Dict]:
    """Extract all efficiency metrics for each scenario"""
    scenario_data = []
    
    for result in results:
        monitor_data = result['monitor_data']
        
        all_costs_by_time = extract_total_costs_from_monitor_data(monitor_data)
        total_cost = sum(all_costs_by_time.values()) if all_costs_by_time else 0
        
        total_environmental_impact = total_emissions_kgco2e(monitor_data.get('environmental_history', {}))
        
        collection_metrics = _calculate_collection_metrics(monitor_data)
        processing_metrics = _calculate_processing_metrics(monitor_data, collection_metrics['total_collected'])
        
        cost_per_m3 = total_cost / processing_metrics['total_processed'] if processing_metrics['total_processed'] > 0 else float('inf')
        
        scenario_data.append({
            'scenario': create_scenario_label(result),
            'inventory_policy': result['inventory_policy'],
            'stock_strategy': result['stock_strategy'],
            'total_cost': total_cost,
            'total_environmental_impact': total_environmental_impact,
            'collection_efficiency': collection_metrics['collection_efficiency'],
            'processing_efficiency': processing_metrics['processing_efficiency'],
            'cost_per_m3': cost_per_m3,
            'total_processed': processing_metrics['total_processed']
        })
    
    return scenario_data

def _calculate_collection_metrics(monitor_data: Dict) -> Dict:
    """Calculate collection efficiency metrics"""
    generation_history = monitor_data.get('generation_history', {})
    total_generated = sum(
        last_cumulative_by_entity(generation_history, 'total_potential_generated').values()
    )
    total_outlet = sum(
        last_cumulative_by_entity(generation_history, 'total_outlet').values()
    )
    treatable_potential = total_generated - total_outlet
    total_collected = sum(
        last_cumulative_by_entity(monitor_data.get('collection_history', {}), 'collected_volumes').values()
    )

    collection_efficiency = (
        (total_collected / treatable_potential * 100) if treatable_potential > 0 else 0
    )

    return {
        'total_generated': total_generated,
        'total_collected': total_collected,
        'collection_efficiency': collection_efficiency
    }

def _calculate_processing_metrics(monitor_data: Dict, total_collected: float) -> Dict:
    """Calculate processing efficiency metrics"""
    total_processed = sum(
        last_cumulative_by_entity(monitor_data.get('processing_history', {}), 'processed.total').values()
    )

    processing_efficiency = (total_processed / total_collected * 100) if total_collected > 0 else 0

    return {
        'total_processed': total_processed,
        'processing_efficiency': processing_efficiency
    }

def _create_efficiency_subplot_figure():
    """Create subplot structure"""
    return sp.make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Cost vs Environmental Impact",
            "Cost vs Collection Efficiency",
            "Environmental Impact vs Processing Efficiency",
            "Cost Efficiency by Strategy",
        ],
        horizontal_spacing=0.12,
        vertical_spacing=0.18,
        specs=[
            [{"secondary_y": False}, {"secondary_y": False}],
            [{"secondary_y": False}, {"secondary_y": False}],
        ],
    )

def _add_efficiency_scatter_plots(fig, scenario_data: List[Dict]):
    """Add scatter plots with consistent styling"""
    colors, symbols = POLICY_COLORS, STRATEGY_SYMBOLS

    subplot_configs = [
        {'x': 'total_cost', 'y': 'total_environmental_impact', 'row': 1, 'col': 1, 
         'hover': "Cost: %{x:,.0f}<br>Impact: %{y:,.0f} kg CO₂e"},
        {'x': 'total_cost', 'y': 'collection_efficiency', 'row': 1, 'col': 2,
         'hover': "Cost: %{x:,.0f}<br>Efficiency: %{y:.1f}%"},
        {'x': 'total_environmental_impact', 'y': 'processing_efficiency', 'row': 2, 'col': 1,
         'hover': "Impact: %{x:,.0f} kg CO₂e<br>Efficiency: %{y:.1f}%"}
    ]

    for i, config in enumerate(subplot_configs):
        for data in scenario_data:
            fig.add_trace(
                go.Scatter(
                    x=[data[config["x"]]],
                    y=[data[config["y"]]],
                    mode="markers",
                    marker={
                        "color": colors[data["inventory_policy"]],
                        "symbol": symbols[data["stock_strategy"]],
                        "size": 8,
                        "line": {"width": 1, "color": "white"},
                    },
                    name=f"{data['inventory_policy']} - {data['stock_strategy']}",
                    legendgroup=f"{data['inventory_policy']}_{data['stock_strategy']}",
                    showlegend=(i == 0),
                    hovertemplate=f"<b>{data['scenario']}</b><br>{config['hover']}<extra></extra>",
                ),
                row=config["row"],
                col=config["col"],
            )

    _update_all_subplot_styling(fig)


def _update_all_subplot_styling(fig):
    """Apply consistent styling to all subplots"""

    axis_style = {
        "showgrid": True,
        "gridcolor": "#E5E5E5",
        "gridwidth": 0.5,
        "zeroline": False,
        "showline": True,
        "linecolor": "black",
        "linewidth": 1,
        "tickfont": {"size": 10},
    }

    fig.update_xaxes(title_text="Total Cost", row=1, col=1, **axis_style)
    fig.update_xaxes(title_text="Total Cost", row=1, col=2, **axis_style)
    fig.update_xaxes(
        title_text="Environmental Impact (kg CO₂e)", row=2, col=1, **axis_style
    )
    fig.update_xaxes(title_text="Scenario", row=2, col=2, **axis_style, tickangle=45)

    fig.update_yaxes(
        title_text="Environmental Impact<br>(kg CO₂e)", row=1, col=1, **axis_style
    )
    fig.update_yaxes(title_text="Collection Efficiency (%)", row=1, col=2, **axis_style)
    fig.update_yaxes(title_text="Processing Efficiency (%)", row=2, col=1, **axis_style)
    fig.update_yaxes(title_text="Cost/m³", row=2, col=2, **axis_style)


def _add_cost_efficiency_bar_chart(fig, scenario_data: List[Dict]):
    """Add bar chart"""
    colors = POLICY_COLORS

    sorted_data = sorted(
        scenario_data,
        key=lambda x: (math.isinf(x["cost_per_m3"]), x["cost_per_m3"]),
    )

    scenario_names = [data["scenario"] for data in sorted_data]
    cost_efficiencies = [
        None if math.isinf(data["cost_per_m3"]) else data["cost_per_m3"]
        for data in sorted_data
    ]
    custom_labels = [
        "N/A" if math.isinf(data["cost_per_m3"]) else f"{data['cost_per_m3']:,.2f}"
        for data in sorted_data
    ]
    bar_text = [
        "N/A" if math.isinf(data["cost_per_m3"]) else ""
        for data in sorted_data
    ]
    bar_colors = [colors[data["inventory_policy"]] for data in sorted_data]

    fig.add_trace(
        go.Bar(
            x=scenario_names,
            y=cost_efficiencies,
            text=bar_text,
            textposition="auto",
            customdata=custom_labels,
            marker={
                "color": bar_colors,
                "line": {"color": "white", "width": 1},
            },
            showlegend=False,
            hovertemplate="<b>%{x}</b><br>Cost/m³: %{customdata}<extra></extra>",
        ),
        row=2,
        col=2,
    )


def _create_entity_status_view(results: List[Dict], output_dir: str):
    """Create entity status timeline plots grouped by scenario and inventory policy, with stock strategies as subplots."""

    entity_status_dir = os.path.join(output_dir, "entity_status")
    os.makedirs(entity_status_dir, exist_ok=True)

    def get_status_color(status):
        color_map = {
            'OPERATIONAL': 'green', 'FAILED': 'red', 'RECOVERING': 'orange',
        }
        return color_map.get(status, 'gray')

    def get_status_label(status):
        if status in ('OPERATIONAL', 'FAILED', 'RECOVERING'):
            return status
        return f'UNKNOWN_{status}'

    grouped_results = group_results_by_scenario_and_policy(results)

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
            vertical_spacing = (
                min(0.12, 0.8 / max(1, num_strategies - 1)) if num_strategies > 1 else 0.0
            )

            fig = sp.make_subplots(
                rows=num_strategies, 
                cols=1,
                subplot_titles=[f"Stock Strategy: {result['stock_strategy']}" for result in results_group],
                vertical_spacing=vertical_spacing,
                specs=[[{"secondary_y": False}] for _ in range(num_strategies)]
            )

            max_entities = 0
            seen_legend_keys = set()

            for subplot_idx, result in enumerate(results_group, 1):
                monitor_data = result['monitor_data']
                history_dict = monitor_data[config['history_key']]

                entity_list = sorted(history_dict.keys())
                entity_positions = {entity: idx for idx, entity in enumerate(entity_list)}
                max_entities = max(max_entities, len(entity_list))

                if not entity_list:
                    continue

                fig.update_yaxes(
                    tickvals=list(range(len(entity_list))),
                    ticktext=entity_list,
                    row=subplot_idx,
                    col=1,
                )

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

                        segments.append((start_idx, len(statuses), current_status))

                    for seg_start, seg_end, seg_status in segments:
                        # Extend to next timestamp to bridge transition gaps; lines+markers keeps 1-tick segments visible.
                        slice_end = min(seg_end + 1, len(timestamps))
                        seg_timestamps = timestamps[seg_start:slice_end]
                        seg_y = [y_position] * len(seg_timestamps)
                        status_label = get_status_label(seg_status)
                        show_legend = status_label not in seen_legend_keys
                        seen_legend_keys.add(status_label)

                        fig.add_trace(
                            go.Scatter(
                                x=seg_timestamps,
                                y=seg_y,
                                mode='lines+markers',
                                line={'color': get_status_color(seg_status), 'width': 4},
                                marker={'color': get_status_color(seg_status), 'size': 5},
                                name=status_label,
                                legendgroup=status_label,
                                showlegend=show_legend,
                                hovertemplate=f"Entity: {entity_name}<br>Status: {status_label}<br>Time: %{{x}}<extra></extra>"
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

            for i in range(1, num_strategies + 1):
                fig.update_xaxes(title_text="Time", row=i, col=1)
                fig.update_yaxes(title_text=config['y_title'], row=i, col=1)

            filename = f"{config['filename_prefix']}_{file_id}"
            save_plot_files(fig, entity_status_dir, filename)
