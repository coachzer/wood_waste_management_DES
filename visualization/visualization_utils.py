import logging
import os

import numpy as np
from typing import Dict, List
from config.constants import HEATMAP_TIME_GRID_POINTS, PDF_EXPORT_SCALE


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

def create_scenario_label(result: Dict) -> str:
    """Create a standardized scenario label from result data"""
    return f"{result['inventory_policy']} | {result['stock_strategy']}"

def save_plot_files(fig, output_dir: str, filename: str, print_message: str = None):
    """Save HTML and PDF versions of a plot"""
    os.makedirs(output_dir, exist_ok=True)

    fig.write_html(f"{output_dir}/{filename}.html")

    safe_write_image(fig, f"{output_dir}/{filename}.pdf", scale=PDF_EXPORT_SCALE)

    if print_message:
        logging.info(print_message)
    else:
        logging.info(f"Plot saved: {filename}")

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

def _validate_entity_series(entity_name: str, series_name: str,
                            timestamps: List[float], values: List[float]):
    """Reject corrupted monitor history instead of silently misplotting it."""
    if len(timestamps) != len(values):
        raise ValueError(
            f"Series '{series_name}' of entity '{entity_name}' has "
            f"{len(values)} values for {len(timestamps)} timestamps"
        )
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError(
            f"Timestamps of entity '{entity_name}' are not strictly increasing"
        )


def aggregate_aligned_series(series_by_entity: Dict, series_class: str) -> Dict:
    """Aggregate per-entity time series on the union of their timestamps.

    ``series_by_entity`` maps an entity name to a ``(timestamps, values)``
    pair. The monitor loop currently samples every entity on one shared
    cadence, so the per-entity timestamp vectors are identical and this
    alignment is a no-op — but that is an accident of the sampling schedule,
    not a contract. Event-driven tracking (``track_processing`` is also called
    from the treatment intake path) can introduce per-entity timestamps at any
    time, and a plain ``{timestamp: sum}`` dict then drops each absent
    entity's contribution, sawing the aggregate curve downward (VIZ-REVIEW T4).

    Gap semantics depend on what the series measures (``series_class``):

    - ``'cumulative'`` (running totals): forward-fill; an entity contributes
      zero before its first observation. Result is the sum across entities.
    - ``'level'`` (sampled stock levels): forward-fill; the first observed
      value is extended backward (a primed buffer existed before the monitor
      first sampled it). Result is the sum across entities.
    - ``'rate'`` (sampled state variables such as efficiency): forward-fill,
      then average; an entity is excluded from the mean before its first
      observation. Forward-filling before averaging keeps a single entity's
      off-cadence sample from collapsing the mean to its own value.

    Per-tick increments (costs, emissions) must NOT be routed through this
    helper: their alignment-safe aggregation is a plain sum-then-cumsum, and
    forward-filling them would double-count.
    """
    if series_class not in ('cumulative', 'level', 'rate'):
        raise ValueError(f"Unknown series class '{series_class}'")

    for entity_name, (timestamps, values) in series_by_entity.items():
        _validate_entity_series(entity_name, series_class, timestamps, values)

    union_times = sorted({t for timestamps, _ in series_by_entity.values() for t in timestamps})

    aligned_values = []
    for t in union_times:
        contributions = []
        for timestamps, values in series_by_entity.values():
            index = np.searchsorted(timestamps, t, side='right') - 1
            if index >= 0:
                contributions.append(values[index])
            elif series_class == 'cumulative':
                contributions.append(0.0)
            elif series_class == 'level' and values:
                contributions.append(values[0])
            # 'rate': excluded from the mean before first observation
        if series_class == 'rate':
            aligned_values.append(float(np.mean(contributions)) if contributions else 0.0)
        else:
            aligned_values.append(float(sum(contributions)))

    return {'timestamps': union_times, 'values': aligned_values}


def _sum_series_per_entity(history: Dict, series_key: str) -> Dict:
    """Collapse each entity's per-waste-type series into one summed series."""
    series_by_entity = {}
    for entity_name, data in history.items():
        timestamps = data.get('timestamps', [])
        per_type = data.get(series_key, {})
        for type_name, values in per_type.items():
            _validate_entity_series(entity_name, f"{series_key}[{type_name}]",
                                    timestamps, values)
        summed = [sum(values[i] for values in per_type.values())
                  for i in range(len(timestamps))]
        series_by_entity[entity_name] = (timestamps, summed)
    return series_by_entity


def aggregate_generation_data(history: Dict) -> Dict:
    """Aggregate cumulative generated volume across all generators"""
    aligned = aggregate_aligned_series(
        _sum_series_per_entity(history, 'total_generated'), 'cumulative'
    )
    return {'timestamps': aligned['timestamps'], 'volumes': aligned['values']}

def aggregate_collection_data(history: Dict) -> Dict:
    """Aggregate cumulative collected volume across all collectors"""
    aligned = aggregate_aligned_series(
        _sum_series_per_entity(history, 'collected_volumes'), 'cumulative'
    )
    return {'timestamps': aligned['timestamps'], 'volumes': aligned['values']}

def calculate_average_efficiency(history: Dict) -> Dict:
    """Calculate average efficiency (a sampled state variable) over time"""
    series_by_entity = {
        entity_name: (data.get('timestamps', []), data.get('efficiency', []))
        for entity_name, data in history.items()
    }
    aligned = aggregate_aligned_series(series_by_entity, 'rate')
    return {'timestamps': aligned['timestamps'], 'efficiency': aligned['values']}

def calculate_storage_levels(history: Dict) -> Dict:
    """Calculate total storage level (a sampled stock) at each timestamp"""
    series_by_entity = {
        entity_name: (data.get('timestamps', []),
                      data.get('storage', {}).get('total', []))
        for entity_name, data in history.items()
    }
    aligned = aggregate_aligned_series(series_by_entity, 'level')
    return {'timestamps': aligned['timestamps'], 'storage': aligned['values']}