from config.base_config import get_cost_params
from typing import Dict, Tuple
from config.constants import (
    LANDFILL_EMISSIONS_PER_M3_KG,
    LANDFILL_COST_PER_TONNE_USD,
    KILOGRAMS_PER_TONNE,
    WASTE_DENSITIES,
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
    
def compute_and_handle_overflow(
    entity,
    original_amounts: Dict[WasteType, float],
    allowed_amounts: Dict[WasteType, float],
) -> None:
    """Route the per-type overflow skimmed by check_storage_capacity to handle_storage_event.

    check_storage_capacity already scaled each type proportionally, so the
    per-type overflow is exactly what was skimmed off each stream. Sorted by
    WasteType.value for deterministic iteration (CRN guard).
    """
    per_type_overflow = {
        waste_type: original_amounts[waste_type]
        - allowed_amounts.get(waste_type, 0.0)
        for waste_type in sorted(
            original_amounts, key=lambda waste_type: waste_type.value
        )
    }
    handle_storage_event(entity, per_type_overflow)


def split_overflow_by_type(
    composition: Dict[WasteType, float],
    overflow_total: float,
) -> Dict[WasteType, float]:
    """Apportion a scalar overflow volume across waste types proportionally.

    Used by callers that know the composition of the storage being truncated but
    only have a scalar overflow total. The split preserves the same type-ratio
    check_storage_capacity scales additions by, so each type contributes
    overflow_total * (vol_m3 / total_composition); the per-type landfill-cost
    path can then weight each type by its own density (ADR 0013).

    The composition is consumed in sorted(key=WasteType.value) order to keep
    arithmetic deterministic across processes (the CRN guard -- enum members hash
    by id(), so unsorted set/dict-of-enum iteration silently breaks reproducibility).
    """
    total_composition = sum(composition.values())
    if total_composition <= 0.0:
        return {
            waste_type: 0.0
            for waste_type in sorted(composition, key=lambda item: item.value)
        }
    return {
        waste_type: overflow_total * (volume_m3 / total_composition)
        for waste_type, volume_m3 in sorted(
            composition.items(), key=lambda item: item[0].value
        )
    }


def handle_storage_event(entity, composition: Dict[WasteType, float], force_landfill=False):
    """Resolve a storage overflow by either expanding capacity or landfilling.

    ``composition`` is the per-WasteType breakdown of the overflowing volume (m³).
    The expand-vs-landfill decision and the landfilled-mass attribution use the
    total over all types, while the landfill cost weights each type by its own
    bulk density (ADR 0013) -- low-density streams (e.g. sawdust at 200 kg/m³)
    cost proportionally less to landfill than dense ones at the flat-rate ceiling.

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
    if composition is None:
        raise ValueError("Composition cannot be None for overflow handling")
    total_volume = sum(composition.values())
    if total_volume < 0:
        raise ValueError("Overflow volume must be non-negative")
    if total_volume < OVERFLOW_VOLUME_TOLERANCE_M3:
        return 0.0, "no_action"

    config = get_cost_params()
    expansion_count = getattr(entity, 'expansion_count', 0)
    landfill_count = getattr(entity, 'landfill_count', 0)

    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (
        1 + expansion_count * config.expansion_cost_escalation_per_prior
    )

    # Per-type landfill cost: each stream's volume is converted to mass at its own
    # bulk density (WASTE_DENSITIES, kg/m³) before the per-tonne gate cost applies,
    # then escalated by prior landfills on this entity. Sorted by WasteType.value
    # so the summation order is deterministic across processes (CRN guard).
    landfill_cost_escalation = (
        1 + landfill_count * config.landfill_cost_escalation_per_prior
    )
    base_landfill_cost = sum(
        volume_m3 * (WASTE_DENSITIES[waste_type] / KILOGRAMS_PER_TONNE)
        * LANDFILL_COST_PER_TONNE_USD
        for waste_type, volume_m3 in sorted(
            composition.items(), key=lambda item: item[0].value
        )
    )
    landfill_cost = base_landfill_cost * landfill_cost_escalation

    expansion_cost = EXPANSION_SIZE_M3 * expansion_cost_per_m3

    if force_landfill or expansion_cost >= landfill_cost:
        entity.landfill_count = landfill_count + 1
        entity.landfill_costs = getattr(entity, 'landfill_costs', 0) + landfill_cost

        # Attribute the landfilled raw waste to the dumping entity so the
        # collection-center mass-balance invariant can account for it (ADR 0009).
        state = getattr(entity, 'state', None)
        if state is not None:
            state.track_waste_landfilled(entity.name, total_volume)

        emissions = total_volume * LANDFILL_EMISSIONS_PER_M3_KG

        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
                volume=total_volume,
                strategy="landfill",
                cost_incurred=landfill_cost,
                timestamp=entity.env.now,
            )

            entity.waste_monitor.track_environmental_impact(
                entity_name=entity.name,
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
                volume=total_volume,
                strategy="expand_storage",
                cost_incurred=expansion_cost,
                timestamp=entity.env.now,
            )

        return expansion_cost, "expand_storage"
