import numpy as np
from models.enums import WasteType
from models.state import SimulationState

def get_furniture_material_quality(waste_type):
    """Define furniture material quality ratings"""
    if waste_type == WasteType.CONSTRUCTION_WOOD:
        return 1.0
    elif waste_type == WasteType.WOOD_CUTTINGS:
        return 0.9
    else:
        return 0.8

def get_transformation_efficiency(treatment_operator, input_type, transformation):
    """Calculate transformation efficiency with uncertainty if applicable"""
    efficiency = transformation.conversion_efficiency
    if treatment_operator.uncertainty_set:
        # Get treatment conversion uncertainty for input type
        mean, std = treatment_operator.uncertainty_set.treatment_conversion.get(
            input_type,
            (efficiency, 0.05),  # Default 5% variation if not specified
        )
        # Apply stochastic variation within reasonable bounds
        efficiency = np.clip(treatment_operator.rng.normal(mean, std), 0.6, 1.0)
    return efficiency

def calculate_output_amounts(treatment_operator, amount_to_process, efficiency):
    """Calculate actual processing and output amounts considering capacity constraints"""
    potential_output = amount_to_process * efficiency
    available_capacity = treatment_operator.storage_capacity - treatment_operator.current_storage
    
    if potential_output > available_capacity:
        scaling_factor = available_capacity / potential_output
        amount_to_process *= scaling_factor
        output_amount = available_capacity
        # Track overflow through data collector
        overflow_amount = potential_output - available_capacity
        treatment_operator.data_collector.track_overflow(
            "treatment",
            overflow_amount,
            "landfill",  # Use landfill for full storage update overflow
            treatment_operator.env.now
        )

    else:
        output_amount = potential_output
        
    return amount_to_process, output_amount

def update_waste_storage(treatment_operator, input_type, output_type, amount_to_process, output_amount):
    """Update waste storage and track raw production"""
    # Update input storage and processed volumes
    treatment_operator.waste_storage[input_type] -= amount_to_process
    treatment_operator.processed_volumes[input_type] += amount_to_process
    
    # Store transformed output and update tracking
    treatment_operator.waste_storage[output_type] = (
        treatment_operator.waste_storage.get(output_type, 0.0) + output_amount
    )
    treatment_operator.total_products_created += output_amount

def fulfill_demand(treatment_operator, output_type, output_amount):
    """Fulfill demand for final products"""
    # Get current unmet demand for this specific product type
    state = SimulationState.get_instance()
    product_type = output_type.value.lower()
    unmet_demand = state.target_demands[product_type] - state.total_products[product_type]
    
    # Use the actual unmet demand to limit production
    fulfilled_amount = min(output_amount, unmet_demand)
    if fulfilled_amount > 0:
        treatment_operator.waste_storage[output_type] -= fulfilled_amount
        treatment_operator.demand -= fulfilled_amount
        
        # Record fulfilled amount in production history with product type
        treatment_operator.production_history.append((treatment_operator.env.now, output_type.value.lower(), fulfilled_amount))
        
        # Report production to simulation state with current time
        state.track_product_production(product_type, fulfilled_amount, treatment_operator.env.now)
        
        print(
            f"{treatment_operator.env.now}: Fulfilled {fulfilled_amount:.2f} m³ of {output_type.value} demand "
            f"(Total: {state.total_products[product_type]:.2f}/{state.target_demands[product_type]:.2f})"
        )

def track_processing_costs(treatment_operator, amount_to_process, transformation):
    """Track energy and operational costs"""
    energy_cost = (
        amount_to_process
        * transformation.energy_required
        * treatment_operator.energy_consumption
    )
    operational_cost = amount_to_process * treatment_operator.operational_costs
    # Track costs through data collector
    treatment_operator.data_collector.track_energy_cost(energy_cost, treatment_operator.env.now)
    treatment_operator.data_collector.track_processing_cost(operational_cost, treatment_operator.env.now)

def update_utilization_metrics(treatment_operator, amount_to_process):
    """Update utilization history for capacity management"""
    current_utilization = amount_to_process / treatment_operator.processing_capacity
    treatment_operator.utilization_history.append(current_utilization)
    if len(treatment_operator.utilization_history) > treatment_operator.utilization_window:
        treatment_operator.utilization_history.pop(0)

def calculate_required_waste(treatment_operator):
    """Calculate how much waste needs to be collected based on unmet demand"""
    if treatment_operator.demand < treatment_operator.minimum_required_waste:
        return 0.0
        
    available_storage = treatment_operator.storage_capacity - treatment_operator.current_storage
    if available_storage <= 0:
        return 0.0
        
    # Calculate required waste based on unmet demand and conversion rate
    required_waste = treatment_operator.demand / treatment_operator.conversion_rate
    
    # Limit by available storage with buffer
    return min(required_waste, available_storage * 0.8)
