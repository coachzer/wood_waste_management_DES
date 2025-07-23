from config.base_config import get_cost_params
from core.overflow import OverflowTracker, OverflowStrategy
from typing import Dict, Tuple, Optional, TypeVar
from dataclasses import dataclass
from models.enums import WasteType
import sys

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
    """
    Apply capacity constraints to determine how much additional amount can be added.
    
    Args:
        current_total: Current total amount
        additional_amount: Amount attempting to add
        capacity: Maximum capacity
        
    Returns:
        CapacityResult with allowed and overflow amounts
    """
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
    """
    Apply capacity constraints to a partial update of values.
    
    Args:
        current_values: Dictionary of current values
        updates: Dictionary of updates to apply
        capacity: Maximum total capacity
        excluded_keys: Optional set of keys to exclude from current total calculation
        
    Returns:
        CapacityResult with scaled updates and overflow information
    """
    excluded_keys = excluded_keys or set()
    
    # Calculate current total excluding specified keys
    current_total = sum(
        amount for key, amount in current_values.items()
        if key not in excluded_keys
    )
    
    # Calculate total of updates
    update_total = sum(updates.values())
    
    # Calculate what can be added
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
        
    # Scale updates proportionally
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

def handle_overflow_with_decision(entity, volume, region):
    
    if entity is None:
        print("[DEBUG] entity is None in handle_overflow_with_decision. Args:")
        print(f"volume: {volume}, region: {region}")
        raise SystemExit("Entity cannot be None for overflow handling")
    
    config = get_cost_params()

    # Track how many times expansion has occurred for this entity
    expansion_count = getattr(entity, 'expansion_count', 0)
    base_expansion_cost_per_m3 = config.expansion_cost_per_m3
    expansion_cost_per_m3 = base_expansion_cost_per_m3 * (10 * expansion_count)
    expansion_cost = volume * expansion_cost_per_m3
    landfill_cost = volume * config.landfill_per_m3

    
    tracker = OverflowTracker()
    FIXED_EXPANSION_AMOUNT = 10000.0
    # Only expand storage if entity is not None
    if entity is not None and expansion_cost < landfill_cost:
        cost, _ = tracker.track_overflow(
            facility_type=getattr(entity, 'facility_type', 'generator'),
            volume=FIXED_EXPANSION_AMOUNT,
            strategy=OverflowStrategy.EXPAND_STORAGE,
            region=region
        )
        entity.waste_storage_capacity += FIXED_EXPANSION_AMOUNT
        # Note: Expansion costs are tracked both per entity (here) and globally in OverflowTracker
        entity.expansion_costs = getattr(entity, 'expansion_costs', 0) + cost
        entity.expansion_count = expansion_count + 1
        return cost, "expand_storage"
    else:
        # Send to landfill using tracker
        cost, _ = tracker.track_overflow(
            facility_type=getattr(entity, 'facility_type', 'generator') if entity is not None else 'generator',
            volume=volume,
            strategy=OverflowStrategy.LANDFILL,
            region=region
        )
        return cost, "landfill"

def check_storage_capacity(
    current_storage: Dict[WasteType, float],
    additions: Dict[WasteType, float],
    capacity: float
) -> Tuple[Dict[WasteType, float], float]:
    """
    Check if adding new amounts would exceed storage capacity and scale if needed.
    
    Args:
        current_storage: Current storage amounts by waste type
        additions: Proposed additions by waste type
        capacity: Maximum storage capacity
        
    Returns:
        Tuple of (allowed additions, overflow amount)
    """
    current_total = sum(current_storage.values())
    addition_total = sum(additions.values())
    
    result = apply_capacity_constraints(current_total, addition_total, capacity)
    
    if result.overflow_amount > 0:
        # Scale additions proportionally
        scaling_factor = result.allowed_amount / addition_total
        allowed_additions = {
            waste_type: amount * scaling_factor
            for waste_type, amount in additions.items()
        }
    else:
        allowed_additions = dict(additions)
        
    return allowed_additions, result.overflow_amount
