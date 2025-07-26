from typing import Dict, Tuple
from enum import Enum
from config.constants import LANDFILL_EMISSIONS_PER_M3

class DecisionStrategy(Enum):
    """Available strategies for handling overflow."""
    LANDFILL = "landfill"  
    EXPAND_STORAGE = "expand_storage"  

class DecisionTracker:
    """Central manager for tracking overflow and calculating penalties."""

    def __init__(self):
        self.landfill_history: Dict[str, float] = {
            "generator": 0.0,
            "collector": 0.0,
            "treatment": 0.0,
        }
        self.total_landfilled: float = 0.0
        self.total_landfill_emissions: float = 0.0
        self.LANDFILL_EMISSIONS_PER_M3 = LANDFILL_EMISSIONS_PER_M3
        self.base_penalty_rate: float = 100.0  
        self.storage_expansion_cost: float = 250.0  
        self.strategy_costs: Dict[str, float] = {
            "landfill_penalties": 0.0,
            "storage_expansion": 0.0
        }
        self.overflow_timeline = []

    def track_overflow(self, 
                       facility_type: str, 
                       volume: float, 
                       strategy: DecisionStrategy = DecisionStrategy.LANDFILL, 
                       timestamp=None, 
                       region=None) -> Tuple[float, str]:
        """
        Tracks overflow volume and handles it according to the specified strategy, with region info.
        Returns: (cost, message) tuple with the cost incurred and status message.
        """
        # Validate facility_type
        if facility_type not in self.landfill_history:
            raise ValueError(f"Invalid facility type: {facility_type}")

        # Validate volume
        if not isinstance(volume, (int, float)) or volume < 0:
            raise ValueError(f"Volume must be a non-negative number, got: {volume}")

        # Validate strategy
        if not isinstance(strategy, DecisionStrategy):
            raise ValueError(f"Strategy must be a DecisionStrategy enum, got: {strategy}")

        # Validate timestamp (if provided)
        if timestamp is not None and not isinstance(timestamp, (int, float)):
            raise ValueError(f"Timestamp must be a number or None, got: {timestamp}")

        # Validate region (if provided)
        if region is not None and not isinstance(region, str):
            raise ValueError(f"Region must be a string or None, got: {region}")

        # Track region in a new history dict
        if not hasattr(self, "overflow_region_history"):
            self.overflow_region_history = {}
        if facility_type not in self.overflow_region_history:
            self.overflow_region_history[facility_type] = []
        self.overflow_region_history[facility_type].append({
            "volume": volume,
            "strategy": strategy.value if isinstance(strategy, DecisionStrategy) else str(strategy),
            "region": region
        })

        self.overflow_timeline.append({
            'timestamp': timestamp or 0,
            'facility_type': facility_type,
            'volume': volume,
            'strategy': strategy.value if isinstance(strategy, DecisionStrategy) else str(strategy),
            'region': region
        })

        match strategy:
            case DecisionStrategy.LANDFILL:
                return self._handle_landfill(facility_type, volume)
            case DecisionStrategy.EXPAND_STORAGE:
                return self._handle_storage_expansion(volume)
            case _:
                raise ValueError(f"Unknown strategy: {strategy}")

    def _handle_landfill(self, facility_type: str, volume: float) -> Tuple[float, str]:
        """Handle overflow by sending to landfill."""
        self.landfill_history[facility_type] += volume
        self.total_landfilled += volume
        # Track emissions
        emissions = volume * self.LANDFILL_EMISSIONS_PER_M3
        self.total_landfill_emissions += emissions
        # Calculate penalty with escalating severity based on volume
        severity = self._determine_severity(volume)
        penalty = self.calculate_penalty(facility_type, severity, volume)
        self.strategy_costs["landfill_penalties"] += penalty
        return penalty, f"Sent {volume:.2f} units to landfill with {severity} penalty, emissions: {emissions:.2f}"

    def _handle_storage_expansion(self, volume: float) -> Tuple[float, str]:
        """Handle overflow by expanding storage capacity."""
        expansion_cost = volume * self.storage_expansion_cost
        self.strategy_costs["storage_expansion"] += expansion_cost
        return expansion_cost, f"Expanded storage by {volume:.2f} units"

    def _handle_intake_reduction(self, volume: float) -> Tuple[float, str]:
        """Handle overflow by reducing intake temporarily."""
        # This might have indirect costs (lost revenue), but no direct penalty
        return 0.0, f"Reduced intake by {volume:.2f} units"

    def _determine_severity(self, volume: float) -> str:
        """Determine overflow severity based on volume."""
        if volume <= 100.0:
            return "warning"
        elif volume <= 300.0:
            return "critical"
        else:
            return "emergency"

    def calculate_penalty(self, facility_type: str, severity: str, volume: float) -> float:
        """Calculates overflow penalty based on facility type and severity."""
        facility_multiplier = {
            "generator": 1.0,
            "collector": 1.2,
            "treatment": 1.5,
        }.get(facility_type)
        severity_multiplier = {
            "warning": 1.0,
            "critical": 1.5,
            "emergency": 2.0,
        }.get(severity)

        if not facility_multiplier or not severity_multiplier:
            raise ValueError("Invalid facility type or severity level")

        base_penalty = volume * self.base_penalty_rate
        final_penalty = base_penalty * facility_multiplier * severity_multiplier
        return final_penalty

    def get_strategy_costs(self) -> Dict[str, float]:
        """Get cumulative costs for each overflow handling strategy."""
        return dict(self.strategy_costs)
            
    def get_overflow_statistics(self) -> Dict[str, float]:
        """Overflow statistics"""
        stats = {
            "total_landfilled": self.total_landfilled,
            "total_landfill_emissions": self.total_landfill_emissions,
            "total_penalties": self.strategy_costs["landfill_penalties"],
            "total_expansion_costs": self.strategy_costs["storage_expansion"],
            "total_cost": sum(self.strategy_costs.values()),
            "landfill_history": self.landfill_history,
            "strategy_costs": self.strategy_costs,
            "overflow_timeline": self.overflow_timeline  
        }
        if hasattr(self, "overflow_region_history"):
            stats["overflow_region_history"] = self.overflow_region_history
        return stats
