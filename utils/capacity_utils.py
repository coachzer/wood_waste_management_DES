from config.base_config import get_cost_params
from typing import Dict, Tuple
from config.constants import (
    LANDFILL_EMISSIONS_PER_M3_KG,
    EXPANSION_SIZE_M3,
    OVERFLOW_VOLUME_TOLERANCE_M3,
)
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
    
def handle_storage_event(entity, volume, force_landfill=False):
    """Resolve a storage overflow by either expanding capacity or landfilling.

    Called when an entity's storage would exceed waste_storage_capacity. Compares
    the cost of one fixed expansion (EXPANSION_SIZE_M3 of new capacity) against the
    cost of landfilling the whole overflow volume and takes the cheaper option;
    force_landfill=True skips the comparison and always landfills (used to dump a
    remainder when expanding is not worthwhile, e.g. after a prior expansion).

    Both unit costs escalate with prior use of that option on this entity:
    expansion by (1 + expansion_count * 0.5) and landfill by
    (1 + landfill_count * 0.3), so repeatedly overflowing the same entity becomes
    progressively more expensive.

    Mutates the entity in place on whichever branch is taken: bumps expansion_count
    / landfill_count, accumulates expansion_costs / landfill_costs, and on the
    expand branch grows waste_storage_capacity by EXPANSION_SIZE_M3. On the landfill
    branch it also attributes the landfilled volume to the entity via
    state.track_waste_landfilled (the mass-balance discard term, ADR 0009) when the
    entity carries a state.

    Monitoring is best-effort: if the entity has a truthy waste_monitor, the chosen
    action and (on landfill) its emissions are recorded; a monitor-less entity is
    handled identically minus the recording.

    Returns (cost_incurred, action) where action is "no_action" (volume below
    tolerance), "expand_storage", or "landfill".
    """
    if entity is None:
        raise ValueError("Entity cannot be None for overflow handling")
    if volume is None or volume < 0:
        raise ValueError("Volume must be a non-negative number")
    if volume < OVERFLOW_VOLUME_TOLERANCE_M3:
        return 0.0, "no_action"

    config = get_cost_params()
    expansion_count = getattr(entity, 'expansion_count', 0)
    landfill_count = getattr(entity, 'landfill_count', 0)

    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (
        1 + expansion_count * config.expansion_cost_escalation_per_prior
    )

    base_landfill_cost_per_m3 = config.landfill_per_m3
    landfill_cost_per_m3 = base_landfill_cost_per_m3 * (
        1 + landfill_count * config.landfill_cost_escalation_per_prior
    )

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
