import numpy as np
from typing import Dict

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
    """Extract collection center storage data"""
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
        if 'collected_volumes' in entity_data:
            timestamps = entity_data['timestamps']
            total_volumes = []
            for _ in timestamps:
                total = sum(sum(volumes) if isinstance(volumes, list) else volumes 
                          for volumes in entity_data['collected_volumes'].values())
                total_volumes.append(min(total / 1000 * 100, 100))  # Normalize to percentage
            
            if total_volumes:
                interpolated = np.interp(time_range, timestamps, total_volumes)
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

def extract_processor_product_storage_data(history: Dict) -> Dict:
    """Extract product storage utilization for processors"""
    return _extract_processor_storage_data(history, 'product_utilization')

def extract_processor_product_to_sell_storage_data(history: Dict) -> Dict:
    """Extract product-to-sell storage utilization for processors"""
    return _extract_processor_storage_data(history, 'product_to_sell_utilization')

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
    avg_efficiency = [np.mean(time_efficiency[t]) for t in sorted_times]
    return {
        'timestamps': sorted_times,
        'efficiency': avg_efficiency
    }

def calculate_processing_throughput(history: Dict) -> Dict:
    """Calculate cumulative processing throughput"""
    time_throughput = {}
    for _, data in history.items():
        timestamps = data.get('timestamps', [])
        processed_total = data.get('processed', {}).get('total', [])
        for t, p in zip(timestamps, processed_total):
            if t not in time_throughput:
                time_throughput[t] = 0
            time_throughput[t] += p
    sorted_times = sorted(time_throughput.keys())
    cumulative = 0
    cumulative_processed = []
    for t in sorted_times:
        cumulative += time_throughput[t]
        cumulative_processed.append(cumulative)
    return {
        'timestamps': sorted_times,
        'processed': cumulative_processed
    }

def find_pareto_front(points):
    """Return a boolean mask for Pareto front points (minimize both objectives)"""
    is_pareto = np.ones(points.shape[0], dtype=bool)
    for i, point in enumerate(points):
        if is_pareto[i]:
            is_pareto[is_pareto] = np.any(points[is_pareto] < point, axis=1)
            is_pareto[i] = True  
    return is_pareto
