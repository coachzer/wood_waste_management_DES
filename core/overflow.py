from typing import Dict, Tuple, Optional
from enum import Enum

class OverflowStrategy(Enum):
    """Available strategies for handling overflow."""
    LANDFILL = "landfill"  # Default - sends to landfill with penalty
    EXPAND_STORAGE = "expand_storage"  # Increase storage capacity at a cost
    EMERGENCY_TRANSPORT = "emergency_transport"  # Transport to alternative facility
    REDUCE_INTAKE = "reduce_intake"  # Temporarily reduce waste intake

class OverflowTracker:
    """Central manager for tracking overflow and calculating penalties."""

    def __init__(self):
        self.landfill_history: Dict[str, float] = {
            "generator": 0.0,
            "collector": 0.0,
            "treatment": 0.0,
        }
        self.total_landfilled: float = 0.0
        self.base_penalty_rate: float = 100.0  # Base penalty per unit of overflow
        self.storage_expansion_cost: float = 250.0  # Cost per unit of storage expansion
        self.emergency_transport_cost: float = 400.0  # Cost per unit for emergency transport

        # Track cumulative costs by strategy
        self.strategy_costs: Dict[str, float] = {
            "landfill_penalties": 0.0,
            "storage_expansion": 0.0,
            "emergency_transport": 0.0
        }

    def track_overflow(self, facility_type: str, volume: float, strategy: OverflowStrategy = OverflowStrategy.LANDFILL) -> Tuple[float, str]:
        """
        Tracks overflow volume and handles it according to the specified strategy.
        Returns: (cost, message) tuple with the cost incurred and status message.
        """
        if facility_type not in self.landfill_history:
            raise ValueError(f"Invalid facility type: {facility_type}")

        if strategy == OverflowStrategy.LANDFILL:
            return self._handle_landfill(facility_type, volume)
        elif strategy == OverflowStrategy.EXPAND_STORAGE:
            return self._handle_storage_expansion(volume)
        elif strategy == OverflowStrategy.EMERGENCY_TRANSPORT:
            return self._handle_emergency_transport(volume)
        elif strategy == OverflowStrategy.REDUCE_INTAKE:
            return self._handle_intake_reduction(volume)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _handle_landfill(self, facility_type: str, volume: float) -> Tuple[float, str]:
        """Handle overflow by sending to landfill."""
        self.landfill_history[facility_type] += volume
        self.total_landfilled += volume
        
        # Calculate penalty with escalating severity based on volume
        severity = self._determine_severity(volume)
        penalty = self.calculate_penalty(facility_type, severity, volume)
        
        self.strategy_costs["landfill_penalties"] += penalty
        return penalty, f"Sent {volume:.2f} units to landfill with {severity} penalty"

    def _handle_storage_expansion(self, volume: float) -> Tuple[float, str]:
        """Handle overflow by expanding storage capacity."""
        expansion_cost = volume * self.storage_expansion_cost
        self.strategy_costs["storage_expansion"] += expansion_cost
        return expansion_cost, f"Expanded storage by {volume:.2f} units"

    def _handle_emergency_transport(self, volume: float) -> Tuple[float, str]:
        """Handle overflow through emergency transport."""
        transport_cost = volume * self.emergency_transport_cost
        self.strategy_costs["emergency_transport"] += transport_cost
        return transport_cost, f"Emergency transported {volume:.2f} units"

    def _handle_intake_reduction(self, volume: float) -> Tuple[float, str]:
        """Handle overflow by reducing intake temporarily."""
        # This might have indirect costs (lost revenue), but no direct penalty
        return 0.0, f"Reduced intake by {volume:.2f} units"

    def _determine_severity(self, volume: float) -> str:
        """Determine overflow severity based on volume."""
        if volume <= 10.0:
            return "warning"
        elif volume <= 30.0:
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
        """Get comprehensive overflow statistics."""
        return {
            "total_landfilled": self.total_landfilled,
            "total_penalties": self.strategy_costs["landfill_penalties"],
            "total_expansion_costs": self.strategy_costs["storage_expansion"],
            "total_transport_costs": self.strategy_costs["emergency_transport"],
            "total_cost": sum(self.strategy_costs.values())
        }
