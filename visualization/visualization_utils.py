import numpy as np
from typing import Dict


def safe_write_image(fig, path, **kwargs):
    try:
        fig.write_image(path, **kwargs)
        return True
    except Exception:
        print(f"PDF export skipped ({path}) -- set BROWSER_PATH to a Chromium executable to enable it")
        return False

def extract_storage_data(history: Dict, metric: str) -> Dict:
    """Extract storage utilization data for heatmap"""
    entities = list(history.keys())
    if not entities:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    all_timestamps = []
    for entity_data in history.values():
        if 'timestamps' in entity_data:
            all_timestamps.extend(entity_data['timestamps'])
    
    if not all_timestamps:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
    z_matrix = []
    
    for entity in entities:
        entity_data = history[entity]
        if metric in entity_data and entity_data[metric]:
            timestamps = entity_data['timestamps']
            values = entity_data[metric]
            interpolated = np.interp(time_range, timestamps, values)
            z_matrix.append(interpolated)
        else:
            z_matrix.append(np.zeros(len(time_range)))
    
    return {
        'x_values': time_range,
        'y_values': entities,
        'z_values': z_matrix
    }

def extract_collection_storage_data(history: Dict) -> Dict:
    """Extract collection center storage data for heatmap"""
    collectors = list(history.keys())
    timestamps = []
    z_values = []

    for collector_history in history.values():
        timestamps.extend(collector_history.get('timestamps', []))
    timestamps = sorted(set(timestamps))

    for collector in collectors:
        collector_history = history[collector]
        collector_values = []
        for ts in timestamps:
            if ts in collector_history.get('timestamps', []):
                idx = collector_history['timestamps'].index(ts)
                collector_values.append(
                    collector_history.get('storage_utilization', [0]*len(collector_history['timestamps']))[idx]
                )
            else:
                collector_values.append(0)
        z_values.append(collector_values)

    return {
        'z_values': z_values,
        'x_values': timestamps,
        'y_values': collectors
    }

def extract_processing_storage_data(history: Dict) -> Dict:
    """Extract processing facility storage data"""
    entities = list(history.keys())
    if not entities:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    all_timestamps = []
    for entity_data in history.values():
        if 'timestamps' in entity_data:
            all_timestamps.extend(entity_data['timestamps'])
    
    if not all_timestamps:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
    z_matrix = []
    
    for entity in entities:
        entity_data = history[entity]
        if 'storage' in entity_data and 'utilization' in entity_data['storage']:
            timestamps = entity_data['timestamps']
            utilization = entity_data['storage']['utilization']
            
            if utilization:
                interpolated = np.interp(time_range, timestamps, utilization)
                z_matrix.append(interpolated)
            else:
                z_matrix.append(np.zeros(len(time_range)))
        else:
            z_matrix.append(np.zeros(len(time_range)))
    
    return {
        'x_values': time_range,
        'y_values': entities,
        'z_values': z_matrix
    }

def extract_processor_waste_storage_data(history: Dict) -> Dict:
    """Extract waste storage utilization for processors"""
    return _extract_processor_storage_data(history, 'waste_utilization')

def extract_processor_finished_goods_storage_data(history: Dict) -> Dict:
    """Extract finished-goods storage utilization for processors"""
    return _extract_processor_storage_data(history, 'finished_goods_utilization')

def _extract_processor_storage_data(history: Dict, metric: str) -> Dict:
    """Helper method for processor storage data extraction"""
    entities = list(history.keys())
    if not entities:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    all_timestamps = []
    for entity_data in history.values():
        if 'timestamps' in entity_data:
            all_timestamps.extend(entity_data['timestamps'])
    
    if not all_timestamps:
        return {'x_values': [], 'y_values': [], 'z_values': []}
    
    time_range = np.linspace(min(all_timestamps), max(all_timestamps), 50)
    z_matrix = []
    
    for entity in entities:
        entity_data = history[entity]
        if 'storage' in entity_data and metric in entity_data['storage']:
            timestamps = entity_data['timestamps']
            utilization = entity_data['storage'][metric]
            if utilization:
                interpolated = np.interp(time_range, timestamps, utilization)
                z_matrix.append(interpolated)
            else:
                z_matrix.append(np.zeros(len(time_range)))
        else:
            z_matrix.append(np.zeros(len(time_range)))
    
    return {
        'x_values': time_range,
        'y_values': entities,
        'z_values': z_matrix
    }

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
    storage_levels = [time_storage[t] for t in sorted_times]  # No cumulative calculation
    
    return {
        'timestamps': sorted_times,
        'storage': storage_levels  
    }