from config.base_config import get_cost_params
from typing import Dict, Tuple
from config.constants import LANDFILL_EMISSIONS_PER_M3
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
    else:
        return dict(additions), addition_total - available_capacity
    
def handle_storage_event(entity, volume, region, force_landfill=False):
    if entity is None:
        raise ValueError("Entity cannot be None for overflow handling")
    if volume is None or volume < 0:
        raise ValueError("Volume must be a non-negative number")
    TOLERANCE = 1e-10  
    if volume < TOLERANCE:
        print(f"DEBUG: Returning early for near-zero volume ({volume})")
        return 0.0, "no_action"
    if region is None:
        raise ValueError("Region cannot be None")
    
    config = get_cost_params()
    expansion_count = getattr(entity, 'expansion_count', 0)
    landfill_count = getattr(entity, 'landfill_count', 0)  

    # Expansion cost increases with each expansion
    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (1 + expansion_count * 0.5)  

    # Landfill cost increases with each landfill usage
    base_landfill_cost_per_m3 = config.landfill_per_m3
    landfill_cost_per_m3 = base_landfill_cost_per_m3 * (1 + landfill_count * 0.3)  # 30% increase per use

    needed_expansion = volume * 1.4
    expansion_cost = needed_expansion * expansion_cost_per_m3
    landfill_cost = volume * landfill_cost_per_m3

    # Check if landfill is forced or if it's the cheaper option
    if force_landfill or expansion_cost >= landfill_cost:
        entity.landfill_count = landfill_count + 1
        entity.landfill_costs = getattr(entity, 'landfill_costs', 0) + landfill_cost

        emissions = volume * (LANDFILL_EMISSIONS_PER_M3 * 1000)   
        
        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
                facility_type=entity.facility_type,
                volume=volume,
                strategy="landfill",
                cost_incurred=landfill_cost,
                timestamp=entity.env.now,
            )
            # Track the environmental impact
            entity.waste_monitor.track_environmental_impact(
                entity_name=entity.name,
                entity_type=entity.facility_type,
                environmental_impact=emissions,
                timestamp=entity.env.now,
                impact_category="landfill_emissions"
            )

        return landfill_cost, "landfill"
    else:
        entity.waste_storage_capacity += needed_expansion
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
