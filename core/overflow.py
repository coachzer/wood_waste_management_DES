from typing import Dict, Tuple
from enum import Enum
from config.base_config import LANDILL_EMISSIONS_PER_M3

class OverflowStrategy(Enum):
    """Available strategies for handling overflow."""
    LANDFILL = "landfill"  # Default - sends to landfill with penalty
    EXPAND_STORAGE = "expand_storage"  # Increase storage capacity at a cost

class OverflowTracker:
    """Central manager for tracking overflow and calculating penalties."""

    def __init__(self):
        self.landfill_history: Dict[str, float] = {
            "generator": 0.0,
            "collector": 0.0,
            "treatment": 0.0,
        }
        self.total_landfilled: float = 0.0
        self.total_landfill_emissions: float = 0.0
        self.LANDILL_EMISSIONS_PER_M3 = LANDILL_EMISSIONS_PER_M3
        self.base_penalty_rate: float = 100.0  # Base penalty per unit of overflow
        self.storage_expansion_cost: float = 250.0  # Cost per unit of storage expansion

        # Track cumulative costs by strategy
        self.strategy_costs: Dict[str, float] = {
            "landfill_penalties": 0.0,
            "storage_expansion": 0.0
        }

    def track_overflow(self, facility_type: str, volume: float, strategy: OverflowStrategy = OverflowStrategy.LANDFILL, region=None) -> Tuple[float, str]:
        """
        Tracks overflow volume and handles it according to the specified strategy, with region info.
        Returns: (cost, message) tuple with the cost incurred and status message.
        """
        if facility_type not in self.landfill_history:
            raise ValueError(f"Invalid facility type: {facility_type}")

        # Track region in a new history dict
        if not hasattr(self, "overflow_region_history"):
            self.overflow_region_history = {}
        if facility_type not in self.overflow_region_history:
            self.overflow_region_history[facility_type] = []
        self.overflow_region_history[facility_type].append({
            "volume": volume,
            "strategy": strategy.value if isinstance(strategy, OverflowStrategy) else str(strategy),
            "region": region
        })

        match strategy:
            case OverflowStrategy.LANDFILL:
                return self._handle_landfill(facility_type, volume)
            case OverflowStrategy.EXPAND_STORAGE:
                return self._handle_storage_expansion(volume)
            case _:
                raise ValueError(f"Unknown strategy: {strategy}")

    def _handle_landfill(self, facility_type: str, volume: float) -> Tuple[float, str]:
        """Handle overflow by sending to landfill."""
        self.landfill_history[facility_type] += volume
        self.total_landfilled += volume
        # Track emissions
        emissions = volume * self.LANDILL_EMISSIONS_PER_M3
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
        """Get comprehensive overflow statistics, including region info if available."""
        stats = {
            "total_landfilled": self.total_landfilled,
            "total_landfill_emissions": self.total_landfill_emissions,
            "total_penalties": self.strategy_costs["landfill_penalties"],
            "total_expansion_costs": self.strategy_costs["storage_expansion"],
            "total_cost": sum(self.strategy_costs.values())
        }
        if hasattr(self, "overflow_region_history"):
            stats["overflow_region_history"] = self.overflow_region_history
        return stats
