"""
Common utilities for capacity checking and overflow handling across the system.
"""
from typing import Dict, Tuple, Optional, TypeVar
from dataclasses import dataclass
from models.enums import WasteType

@dataclass
class CapacityResult:
    """Result of a capacity check operation"""
    allowed_amount: float
    overflow_amount: float
    scaled_values: Optional[Dict] = None

T = TypeVar('T')  # For generic type hints

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

def handle_overflow_generic(
    data_collector,
    facility_type: str,
    overflow_amount: float,
    strategy: str = "landfill",
    current_time: float = None
) -> None:
    """
    Generic handler for overflow situations that interacts with the data collector.
    
    Args:
        data_collector: Instance of DataCollector
        facility_type: Type of facility (e.g., "generator", "collector", "treatment")
        overflow_amount: Amount of overflow to handle
        strategy: Strategy for handling overflow (default: "landfill")
        current_time: Current simulation time (optional)
    """
    if overflow_amount <= 0:
        return
        
    if overflow_amount >= 0.01:  # Only log significant overflow
        print(f"{current_time}: Overflow of {overflow_amount:.2f} m³ from {facility_type}")
        
    data_collector.track_overflow(
        facility_type,
        overflow_amount,
        strategy,
        current_time
    )

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
