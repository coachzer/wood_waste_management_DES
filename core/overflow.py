from typing import Dict


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

    def track_overflow(self, facility_type: str, volume: float):
        """Tracks overflow volume by facility type."""
        if facility_type not in self.landfill_history:
            raise ValueError(f"Invalid facility type: {facility_type}")
        self.landfill_history[facility_type] += volume
        self.total_landfilled += volume

    def calculate_penalty(
        self, facility_type: str, severity: str, volume: float
    ) -> float:
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
