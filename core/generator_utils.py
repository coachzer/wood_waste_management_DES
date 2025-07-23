import numpy as np
from models.state import SimulationState
from utils.capacity_utils import apply_capacity_constraints, apply_partial_update_with_constraints, handle_overflow_with_decision

def calculate_daily_factors(rng, waste_generation_rates, uncertainty_set=None):
    """Calculate daily generation factors based on uncertainty"""
    if not uncertainty_set:
        return [1.0] * len(waste_generation_rates)

    daily_factors = []
    # Use the simplified uncertainty set structure
    variability = getattr(uncertainty_set, 'waste_generation_variability', 0.2)
    
    for _ in waste_generation_rates.keys():
        # Apply variability factor to all waste types uniformly
        factor = rng.normal(1.0, variability)
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

def handle_overflow(env, current_storage, waste_storage_capacity, waste_streams, region, waste_monitor, generator_entity):
    """Handle storage overflow situation"""
    # Create dictionary of current volumes
    current_volumes = {
        waste_type: stream.volume
        for waste_type, stream in waste_streams.items()
    }
    # Use the partial update function to calculate scaled values
    result = apply_partial_update_with_constraints(
        current_values={},  # Empty since we're scaling everything
        updates=current_volumes,
        capacity=waste_storage_capacity
    )
    if result.overflow_amount > 0:
        _, strategy = handle_overflow_with_decision(
            generator_entity,
            result.overflow_amount,
            region
        )
        waste_monitor.track_overflow(
            "generator",
            result.overflow_amount,
            strategy,
            env.now,
            region=region
        )
        # Track waste removal and update waste streams
        state = SimulationState.get_instance()
        total_reduced = 0.0
        for waste_type, stream in waste_streams.items():
            new_volume = result.scaled_values[waste_type]
            reduced_volume = stream.volume - new_volume
            if reduced_volume > 0:
                state.track_waste_collection(region, waste_type, reduced_volume)
                stream.volume = new_volume
                total_reduced += reduced_volume
        current_storage -= total_reduced
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
        # Calculate potential generation amount
        potential_volume = base_rate * seasonal_factor * daily_factor
        
        # Check capacity constraints
        result = apply_capacity_constraints(
            current_total=current_storage,
            additional_amount=potential_volume,
            capacity=current_storage + available_storage
        )

        if result.allowed_amount > 0:
            current_storage = update_waste_stream(
                waste_streams, total_generated, current_storage,
                region, waste_type, result.allowed_amount, current_time,
                history_index, generation_history[waste_type]
            )
            available_storage -= result.allowed_amount

    return available_storage, current_storage, history_index
