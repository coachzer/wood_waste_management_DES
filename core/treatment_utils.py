import numpy as np
from models.state import SimulationState

def get_transformation_efficiency(treatment_operator, transformation):
    """Calculate transformation efficiency with uncertainty if applicable"""
    efficiency = transformation.conversion_efficiency
    if treatment_operator.uncertainty_set:
        if hasattr(treatment_operator.uncertainty_set.treatment_conversion, '__len__') and len(treatment_operator.uncertainty_set.treatment_conversion) == 2:
            mean, std = treatment_operator.uncertainty_set.treatment_conversion
            efficiency = np.clip(treatment_operator.rng.normal(mean * efficiency, std), 0.6, 1.0)
    return efficiency

def calculate_output_amounts(amount_to_process, efficiency):
    """Calculate actual processing and output amounts considering capacity constraints"""
    potential_output = amount_to_process * efficiency
    output_amount = potential_output
    return amount_to_process, output_amount

def update_waste_storage(treatment_operator, input_type, output_type, amount_to_process, output_amount):
    """Update waste storage and track raw production"""
    treatment_operator.waste_storage[input_type] -= amount_to_process
    treatment_operator.processed_volumes[input_type] += amount_to_process
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
        
        # print(
        #     f"{treatment_operator.env.now}: Fulfilled {fulfilled_amount:.2f} m³ of {output_type.value} demand "
        #     f"(Total: {state.total_products[product_type]:.2f}/{state.target_demands[product_type]:.2f})"
        # )

def track_treatment_properties(treatment_operator, amount_to_process, transformation):
    """Track energy and operational costs"""
    energy_cost = (
        amount_to_process
        * transformation.energy_required
        * treatment_operator.energy_consumption
    )
    operational_cost = (
        amount_to_process 
        * treatment_operator.operational_costs
    )
    environmental_impact = (
        amount_to_process 
        * treatment_operator.environmental_impact
    )

    monitor = treatment_operator.waste_monitor
    name = treatment_operator.name
    timestamp = treatment_operator.env.now
    
    monitor.track_cost(name, "treatments", energy_cost, "energy", timestamp)
    monitor.track_cost(name, "treatments", operational_cost, "processing", timestamp)
    monitor.track_environmental_impact(name, "treatments", environmental_impact, timestamp, "impact_cost")

def update_utilization_metrics(treatment_operator, amount_to_process):
    """Update utilization history for capacity management"""
    current_utilization = amount_to_process / treatment_operator.processing_capacity
    treatment_operator.utilization_history.append(current_utilization)
    if len(treatment_operator.utilization_history) > treatment_operator.utilization_window:
        treatment_operator.utilization_history.pop(0)
