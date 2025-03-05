from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum


class CostType(Enum):
    """Types of costs tracked in the system"""

    PROCESSING = "processing"
    TRANSPORTATION = "transportation"
    STORAGE = "storage"
    LANDFILL = "landfill"
    OVERFLOW = "overflow"
    MAINTENANCE = "maintenance"
    ENERGY = "energy"


@dataclass
class CostComponent:
    """Represents a single cost component with its amount and metadata"""

    amount: float
    timestamp: float
    details: Optional[Dict] = None


@dataclass
class CostRecord:
    """Records all costs for a specific type"""

    total: float = 0.0
    history: list[CostComponent] = field(default_factory=list)


class CostTracker:
    """Central manager for tracking all system costs"""

    def __init__(self):
        self.costs: Dict[CostType, CostRecord] = {
            cost_type: CostRecord() for cost_type in CostType
        }

        # Cost rate configurations
        self.rate_config = {
            CostType.PROCESSING: 50.0,  # Base processing cost per unit
            CostType.TRANSPORTATION: 2.0,  # Per unit per km
            CostType.STORAGE: 10.0,  # Per unit per day
            CostType.LANDFILL: 200.0,  # Base landfill cost per unit
            CostType.MAINTENANCE: 100.0,  # Base daily maintenance cost
            CostType.ENERGY: 0.15,  # Cost per kWh
        }

    def track_cost(
        self,
        cost_type: CostType,
        amount: float,
        timestamp: float,
        details: Optional[Dict] = None,
    ):
        """Track a new cost entry"""
        if amount <= 0:
            return

        cost_record = self.costs[cost_type]
        cost_record.total += amount
        cost_record.history.append(
            CostComponent(amount=amount, timestamp=timestamp, details=details)
        )

    def calculate_processing_cost(
        self, volume: float, energy_consumption: float
    ) -> float:
        """Calculate processing cost based on volume and energy consumption"""
        base_cost = volume * self.rate_config[CostType.PROCESSING]
        energy_cost = energy_consumption * self.rate_config[CostType.ENERGY]
        return base_cost + energy_cost

    def calculate_transportation_cost(self, volume: float, distance: float) -> float:
        """Calculate transportation cost based on volume and distance"""
        return volume * distance * self.rate_config[CostType.TRANSPORTATION]

    def calculate_storage_cost(self, volume: float, duration: float) -> float:
        """Calculate storage cost based on volume and duration"""
        return volume * duration * self.rate_config[CostType.STORAGE]

    def calculate_landfill_cost(self, volume: float, distance: float = 0) -> float:
        """Calculate landfill cost including transportation if distance provided"""
        base_cost = volume * self.rate_config[CostType.LANDFILL]
        transport_cost = (
            self.calculate_transportation_cost(volume, distance) if distance > 0 else 0
        )
        return base_cost + transport_cost

    def get_total_cost(self) -> float:
        """Get total cost across all cost types"""
        return sum(record.total for record in self.costs.values())

    def get_cost_breakdown(self) -> Dict[str, float]:
        """Get breakdown of costs by type"""
        return {
            cost_type.value: record.total for cost_type, record in self.costs.items()
        }

    def get_cost_history(self, cost_type: CostType) -> list[CostComponent]:
        """Get historical cost records for a specific cost type"""
        return self.costs[cost_type].history.copy()
