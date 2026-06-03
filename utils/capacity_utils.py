from config.base_config import get_cost_params
from typing import Dict, Tuple
from config.constants import LANDFILL_EMISSIONS_PER_M3_KG, EXPANSION_SIZE_M3
from models.enums import WasteType

def check_storage_capacity(
    current_storage: Dict[WasteType, float],
    additions: Dict[WasteType, float],
    capacity: float
) -> Tuple[Dict[WasteType, float], float]:
    """Check if adding new amounts would exceed storage capacity."""
    current_total = sum(current_storage.values())
    addition_total = sum(additions.values())
    available_capacity = max(0, capacity - current_total)
    
    if addition_total <= available_capacity:
        return dict(additions), 0.0

    if available_capacity <= 0:
        return {waste_type: 0.0 for waste_type in additions}, addition_total

    scale_factor = available_capacity / addition_total
    scaled_additions = {
        waste_type: amount * scale_factor
        for waste_type, amount in additions.items()
    }
    overflow = addition_total - available_capacity
    return scaled_additions, overflow
    
def handle_storage_event(entity, volume, region, force_landfill=False):
    if entity is None:
        raise ValueError("Entity cannot be None for overflow handling")
    if volume is None or volume < 0:
        raise ValueError("Volume must be a non-negative number")
    TOLERANCE = 1e-10
    if volume < TOLERANCE:
        return 0.0, "no_action"
    if region is None:
        raise ValueError("Region cannot be None")
    
    config = get_cost_params()
    expansion_count = getattr(entity, 'expansion_count', 0)
    landfill_count = getattr(entity, 'landfill_count', 0)  
    
    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (1 + expansion_count * 0.5)

    base_landfill_cost_per_m3 = config.landfill_per_m3
    landfill_cost_per_m3 = base_landfill_cost_per_m3 * (1 + landfill_count * 0.3) 

    expansion_cost = EXPANSION_SIZE_M3 * expansion_cost_per_m3
    landfill_cost = volume * landfill_cost_per_m3

    if force_landfill or expansion_cost >= landfill_cost:
        entity.landfill_count = landfill_count + 1
        entity.landfill_costs = getattr(entity, 'landfill_costs', 0) + landfill_cost

        # Attribute the landfilled raw waste to the dumping entity so the
        # collection-center mass-balance invariant can account for it (ADR 0009).
        state = getattr(entity, 'state', None)
        if state is not None:
            state.track_waste_landfilled(entity.name, volume)

        emissions = volume * LANDFILL_EMISSIONS_PER_M3_KG
        
        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
            facility_type=entity.facility_type,
            volume=volume,
            strategy="landfill",
            cost_incurred=landfill_cost,
            timestamp=entity.env.now,
        )

        entity.waste_monitor.track_environmental_impact(
            entity_name=entity.name,
            entity_type=entity.facility_type,
            environmental_impact=emissions,
            timestamp=entity.env.now,
            impact_category="landfill_emissions"
        )

        return landfill_cost, "landfill"
    else:
        entity.waste_storage_capacity += EXPANSION_SIZE_M3  
        entity.expansion_count = expansion_count + 1
        entity.expansion_costs = getattr(entity, 'expansion_costs', 0) + expansion_cost

        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
                facility_type=entity.facility_type,
                volume=volume,
                strategy="expand_storage",
                cost_incurred=expansion_cost,
                timestamp=entity.env.now,
            )

        return expansion_cost, "expand_storage"
