import numpy as np
from models.enums import EntityStatus
from models.state import SimulationState
from utils.capacity_utils import handle_storage_event

def calculate_daily_factors(rng, waste_generation_rates, uncertainty_set=None):
    """Calculate daily generation factors based on uncertainty"""
    if not uncertainty_set:
        return [1.0] * len(waste_generation_rates)

    daily_factors = []
    variability = getattr(uncertainty_set, 'waste_generation_variability', 0.2)
    
    for _ in waste_generation_rates.keys():
        factor = rng.normal(1.0, variability)
        daily_factors.append(np.clip(factor, 0.1, 2.0))
    return daily_factors

def update_waste_stream(waste_streams, total_generated, current_storage, region, waste_type, generated_volume, current_time, history_index, history):
    """Update waste stream and history records"""
    waste_streams[waste_type].volume += generated_volume
    current_storage += generated_volume
    total_generated[waste_type] += generated_volume

    SimulationState.get_instance().track_add_waste(
        region, waste_type, generated_volume
    )

    if history_index >= len(history["times"]):
        history_index = 0

    history["times"][history_index] = current_time
    history["volumes"][history_index] = generated_volume
    history["totals"][history_index] = total_generated[waste_type]
    history["storage"][history_index] = current_storage

    return current_storage

def handle_overflow(current_storage, waste_storage_capacity, waste_streams, region, generator_entity, force_landfill=False):
    """Handle storage overflow situation"""
    
    current_volumes = {
        waste_type: stream.volume
        for waste_type, stream in waste_streams.items()
    }

    total_current = sum(current_volumes.values())
    if total_current > waste_storage_capacity:
        overflow_amount = total_current - waste_storage_capacity
        
        handle_storage_event(
            generator_entity, 
            overflow_amount, 
            region,
            force_landfill=force_landfill
        )
        
        scaling_factor = waste_storage_capacity / total_current
        
        state = SimulationState.get_instance()
        
        for waste_type, stream in waste_streams.items():
            new_volume = stream.volume * scaling_factor
            reduced_volume = stream.volume - new_volume
            if reduced_volume > 0:
                state.track_remove_waste(region, waste_type, reduced_volume)
                stream.volume = new_volume
        
        current_storage = waste_storage_capacity
    
    return current_storage

def generate_waste_for_period(
    name, status, uncertainty_set, waste_generation_rates, region,
    waste_streams, total_generated, generation_history, history_index,
    current_storage, rng, seasonal_factor, available_storage, current_time,
    efficiency=1.0  
):
    """Generate waste for all waste types in one period with efficiency consideration"""
    if uncertainty_set:
        if status == EntityStatus.FAILED:
            return available_storage, current_storage, history_index
        elif status == EntityStatus.RECOVERING:
            print(f"{current_time}: Generator {name} is recovering (efficiency: {efficiency:.2f})")

    daily_factors = calculate_daily_factors(rng, waste_generation_rates, uncertainty_set)

    for (waste_type, base_rate), daily_factor in zip(
        waste_generation_rates.items(), daily_factors
    ):
        potential_volume = base_rate * seasonal_factor * daily_factor * efficiency
        
        if current_storage + potential_volume <= current_storage + available_storage:
            
            current_storage = update_waste_stream(
                waste_streams, total_generated, current_storage,
                region, waste_type, potential_volume, current_time,
                history_index, generation_history[waste_type]
            )
            available_storage -= potential_volume

    return available_storage, current_storage, history_index
