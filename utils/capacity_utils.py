from config.base_config import get_cost_params
from typing import Dict, Tuple, Optional, TypeVar
from dataclasses import dataclass
from models.enums import WasteType

@dataclass
class CapacityResult:
    """Result of a capacity check operation"""
    allowed_amount: float
    overflow_amount: float
    scaled_values: Optional[Dict] = None

T = TypeVar('T') 

def apply_capacity_constraints(
    current_total: float,
    additional_amount: float,
    capacity: float
) -> CapacityResult:
    """Apply capacity constraints to determine how much additional amount can be added. """
    if additional_amount <= 0:
        return CapacityResult(allowed_amount=0, overflow_amount=0)
        
    available_capacity = max(0, capacity - current_total)
    allowed_amount = min(additional_amount, available_capacity)
    overflow_amount = max(0, additional_amount - allowed_amount)
    
    return CapacityResult(
        allowed_amount=allowed_amount,
        overflow_amount=overflow_amount
    )

def apply_partial_update_with_constraints(
    current_values: Dict[T, float],
    updates: Dict[T, float],
    capacity: float,
    excluded_keys: Optional[set] = None
) -> CapacityResult:
    """Apply capacity constraints to a partial update of values."""
    excluded_keys = excluded_keys or set()
    
    current_total = sum(
        amount for key, amount in current_values.items()
        if key not in excluded_keys
    )
    
    update_total = sum(updates.values())
    
    available = capacity - current_total
    if available <= 0:
        return CapacityResult(
            allowed_amount=0,
            overflow_amount=update_total,
            scaled_values=dict(updates)
        )
    
    if update_total <= available:
        return CapacityResult(
            allowed_amount=update_total,
            overflow_amount=0,
            scaled_values=dict(updates)
        )
        
    scaling_factor = available / update_total
    scaled_values = {
        key: amount * scaling_factor
        for key, amount in updates.items()
    }
    
    return CapacityResult(
        allowed_amount=available,
        overflow_amount=update_total - available,
        scaled_values=scaled_values
    )

def handle_storage_event(entity, volume, region):
    if entity is None:
        raise ValueError("Entity cannot be None for overflow handling")
    if volume is None or volume < 0:
        raise ValueError("Volume must be a non-negative number")
    if region is None:
        raise ValueError("Region cannot be None")
    
    config = get_cost_params()
    expansion_count = getattr(entity, 'expansion_count', 0)

    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (1 + expansion_count * 0.5)  # 50% escalation

    needed_expansion = volume * 1.2
    expansion_cost = needed_expansion * expansion_cost_per_m3
    landfill_cost = volume * config.landfill_per_m3

    if expansion_cost < landfill_cost:
        entity.waste_storage_capacity += needed_expansion
        entity.expansion_count = expansion_count + 1
        entity.expansion_costs = getattr(entity, 'expansion_costs', 0) + expansion_cost

        print(f"[STORAGE EXPANSION] {entity.name} expanded by {needed_expansion:.1f} m³. New capacity: {entity.waste_storage_capacity:.1f} m³")

        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
                facility_type=entity.facility_type,
                volume=volume,
                strategy="expand_storage",
                cost_incurred=expansion_cost,
                timestamp=entity.env.now,
            )

        return expansion_cost, "expand_storage"
    else:
        print(f"[LANDFILL] {volume:.1f} m³ sent to landfill from {entity.name}")

        if hasattr(entity, 'waste_monitor') and entity.waste_monitor:
            entity.waste_monitor.track_event(
                facility_type=entity.facility_type,
                volume=volume,
                strategy="landfill",
                cost_incurred=landfill_cost,
                timestamp=entity.env.now,
            )

        return landfill_cost, "landfill"
    
def check_storage_capacity(
    current_storage: Dict[WasteType, float],
    additions: Dict[WasteType, float],
    capacity: float
) -> Tuple[Dict[WasteType, float], float]:
    """Check if adding new amounts would exceed storage capacity and scale if needed."""
    current_total = sum(current_storage.values())
    addition_total = sum(additions.values())
    
    result = apply_capacity_constraints(current_total, addition_total, capacity)
    
    if result.overflow_amount > 0:
        scaling_factor = result.allowed_amount / addition_total
        allowed_additions = {
            waste_type: amount * scaling_factor
            for waste_type, amount in additions.items()
        }
    else:
        allowed_additions = dict(additions)
        
    return allowed_additions, result.overflow_amount
