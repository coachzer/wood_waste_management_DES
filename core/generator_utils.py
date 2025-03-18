import numpy as np
from models.state import SimulationState

def calculate_daily_factors(rng, waste_generation_rates, uncertainty_set=None):
    """Calculate daily generation factors based on uncertainty"""
    if not uncertainty_set:
        return [1.0] * len(waste_generation_rates)

    daily_factors = []
    for waste_type in waste_generation_rates.keys():
        mean, std = uncertainty_set.waste_generation.get(
            waste_type, (1.0, 0.2)
        )
        factor = rng.normal(mean, std)
        daily_factors.append(np.clip(factor, 0.1, 2.0))
    return daily_factors

def update_waste_stream(waste_streams, total_generated, current_storage, region, waste_type, generated_volume, current_time, history_index, history):
    """Update waste stream and history records"""
    waste_streams[waste_type].volume += generated_volume
    current_storage += generated_volume
    total_generated[waste_type] += generated_volume

    # Track waste generation in the region using original region string
    SimulationState.get_instance().track_waste_generation(
        region, waste_type, generated_volume
    )

    if history_index >= len(history["times"]):
        history_index = 0

    history["times"][history_index] = current_time
    history["volumes"][history_index] = generated_volume
    history["totals"][history_index] = total_generated[waste_type]
    history["storage"][history_index] = current_storage

    return current_storage

def handle_overflow(env, name, current_storage, storage_capacity, waste_streams, region, overflow_tracker):
    """Handle storage overflow situation"""
    # Determine severity level
    if current_storage / storage_capacity > 0.95:
        severity = "emergency"
    elif current_storage / storage_capacity > 0.90:
        severity = "critical"
    else:
        severity = "warning"

    # Calculate overflow volume
    overflow_volume = max(0, current_storage - storage_capacity)

    # Landfill the excess waste and track it
    print(
        f"{env.now}: Landfilling {overflow_volume:.2f} m³ of waste from {name}"
    )
    overflow_tracker.track_overflow(
        facility_type="generator", volume=overflow_volume
    )

    # Calculate the reduction factor to bring total storage within capacity
    reduction_factor = storage_capacity / current_storage
    
    # Track waste removal from the region using original region string
    state = SimulationState.get_instance()
    total_reduced = 0.0
    
    # Proportionally reduce each waste stream
    for waste_type in waste_streams:
        current_volume = waste_streams[waste_type].volume
        reduced_volume = current_volume * (1 - reduction_factor)
        if reduced_volume > 0:
            state.track_waste_collection(region, waste_type, reduced_volume)
            waste_streams[waste_type].volume = current_volume - reduced_volume
            total_reduced += reduced_volume
    
    current_storage -= total_reduced

    # Calculate and apply penalty
    penalty = overflow_tracker.calculate_penalty(
        facility_type="generator", severity=severity, volume=overflow_volume
    )
    print(f"Overflow penalty applied to {name}: {penalty:.2f}")
    
    return current_storage

def generate_waste_for_period(
    name, status, uncertainty_set, waste_generation_rates, region,
    waste_streams, total_generated, generation_history, history_index,
    current_storage, rng, seasonal_factor, available_storage, current_time
):
    """Generate waste for all waste types in one period"""
    # Check for failure first
    if uncertainty_set:
        if status == "FAILED":
            print(f"{current_time}: Generator {name} is currently failed, skipping waste generation")
            return available_storage, current_storage, history_index

    daily_factors = calculate_daily_factors(rng, waste_generation_rates, uncertainty_set)

    for (waste_type, base_rate), daily_factor in zip(
        waste_generation_rates.items(), daily_factors
    ):
        if available_storage <= 0:
            break

        generated_volume = min(
            base_rate * seasonal_factor * daily_factor, available_storage
        )

        if generated_volume > 0:
            current_storage = update_waste_stream(
                waste_streams, total_generated, current_storage,
                region, waste_type, generated_volume, current_time,
                history_index, generation_history[waste_type]
            )
            available_storage -= generated_volume

    return available_storage, current_storage, history_index
