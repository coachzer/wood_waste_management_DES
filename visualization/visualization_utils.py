import logging

import numpy as np
from typing import Dict, List
from config.constants import HEATMAP_TIME_GRID_POINTS


def group_results_by_scenario_and_policy(results: List[Dict]) -> Dict:
    """Group results by base scenario name and inventory policy"""
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

    for key in grouped_results:
        grouped_results[key].sort(key=lambda x: x['stock_strategy'])

    return grouped_results

def safe_write_image(fig, path, **kwargs):
    try:
        fig.write_image(path, **kwargs)
        return True
    except Exception:
        logging.warning(
            f"PDF export skipped ({path}) -- Kaleido needs a Chromium runtime; "
            "run kaleido.get_chrome_sync() once to install it"
        )
        return False

def _last_value(series) -> float:
    """Final value of a cumulative series; tolerates bare numbers and empties."""
    if isinstance(series, list):
        return series[-1] if series else 0
    if isinstance(series, (int, float)):
        return series
    return 0

def last_cumulative_by_entity(history: Dict, key: str) -> Dict[str, float]:
    """Sum each entity's final cumulative value under ``key``.

    ``key`` may be a dotted path (``processed.total``). The leaf is either a
    series list (take the last element), a dict of per-type series (sum each
    last element), or a bare number. Cumulative counters make this correct
    regardless of per-entity logging cadence.
    """
    totals = {}
    for entity, data in history.items():
        leaf = data
        for part in key.split('.'):
            leaf = leaf.get(part, {}) if isinstance(leaf, dict) else {}
        if isinstance(leaf, dict):
            totals[entity] = sum(_last_value(series) for series in leaf.values())
        else:
            totals[entity] = _last_value(leaf)
    return totals

def extract_heatmap_matrix(history: Dict, value_selector) -> Dict:
    """Interpolate each entity's series onto a shared time grid for heatmaps.

    ``value_selector(entity_data)`` returns the series to plot (or a falsy
    value, rendered as a zero row).
    """
    entities = list(history.keys())
    if not entities:
        return {'x_values': [], 'y_values': [], 'z_values': []}

    all_timestamps = []
    for entity_data in history.values():
        if 'timestamps' in entity_data:
            all_timestamps.extend(entity_data['timestamps'])

    if not all_timestamps:
        return {'x_values': [], 'y_values': [], 'z_values': []}

    time_range = np.linspace(min(all_timestamps), max(all_timestamps), HEATMAP_TIME_GRID_POINTS)
    z_matrix = []

    for entity in entities:
        entity_data = history[entity]
        values = value_selector(entity_data)
        if values:
            interpolated = np.interp(time_range, entity_data['timestamps'], values)
            z_matrix.append(interpolated)
        else:
            z_matrix.append(np.zeros(len(time_range)))

    return {
        'x_values': time_range,
        'y_values': entities,
        'z_values': z_matrix
    }

def extract_storage_data(history: Dict, metric: str) -> Dict:
    """Extract storage utilization data for heatmap"""
    return extract_heatmap_matrix(history, lambda entity_data: entity_data.get(metric))

def extract_processor_waste_storage_data(history: Dict) -> Dict:
    """Extract waste storage utilization for processors"""
    return extract_heatmap_matrix(
        history, lambda entity_data: entity_data.get('storage', {}).get('waste_utilization')
    )

def extract_processor_finished_goods_storage_data(history: Dict) -> Dict:
    """Extract finished-goods storage utilization for processors"""
    return extract_heatmap_matrix(
        history, lambda entity_data: entity_data.get('storage', {}).get('finished_goods_utilization')
    )

def aggregate_generation_data(history: Dict) -> Dict:
    """Aggregate generation data across all generators"""
    all_timestamps = set()
    all_data = {}
    
    for data in history.values():
        timestamps = data.get('timestamps', [])
        for _, totals in data.get('total_generated', {}).items():
            if len(timestamps) == len(totals):
                for t, v in zip(timestamps, totals):
                    all_timestamps.add(t)
                    if t not in all_data:
                        all_data[t] = 0
                    all_data[t] += v
    
    sorted_times = sorted(all_timestamps)
    return {
        'timestamps': sorted_times,
        'volumes': [all_data[t] for t in sorted_times]
    }

def aggregate_collection_data(history: Dict) -> Dict:
    """Aggregate collection data across all collectors"""
    all_timestamps = set()
    all_data = {}
    
    for collector_data in history.values():
        timestamps = collector_data.get('timestamps', [])
        collected_volumes = collector_data.get('collected_volumes', {})
        
        # For each waste type, aggregate the volumes
        for _, volumes in collected_volumes.items():
            if len(timestamps) == len(volumes):
                for t, v in zip(timestamps, volumes):
                    all_timestamps.add(t)
                    if t not in all_data:
                        all_data[t] = 0
                    all_data[t] += v
    
    sorted_times = sorted(all_timestamps)
    return {
        'timestamps': sorted_times,
        'volumes': [all_data[t] for t in sorted_times]
    }

def calculate_average_efficiency(history: Dict) -> Dict:
    """Calculate average collection efficiency over time"""
    time_efficiency = {}
    for _, data in history.items():
        timestamps = data.get('timestamps', [])
        efficiency = data.get('efficiency', [])
        for t, e in zip(timestamps, efficiency):
            if t not in time_efficiency:
                time_efficiency[t] = []
            time_efficiency[t].append(e)

    sorted_times = sorted(time_efficiency.keys())

    avg_efficiency = [np.mean(time_efficiency[t]) if time_efficiency[t] else 0 for t in sorted_times]
    
    return {
        'timestamps': sorted_times,
        'efficiency': avg_efficiency
    }

def calculate_storage_levels(history: Dict) -> Dict:
    """Calculate total storage levels at each timestamp"""
    time_storage = {}
    for _, data in history.items():
        timestamps = data.get('timestamps', [])
        storage_total = data.get('storage', {}).get('total', [])
        for t, s in zip(timestamps, storage_total):
            if t not in time_storage:
                time_storage[t] = 0
            time_storage[t] += s
    
    sorted_times = sorted(time_storage.keys())
    storage_levels = [time_storage[t] for t in sorted_times]

    return {
        'timestamps': sorted_times,
        'storage': storage_levels
    }