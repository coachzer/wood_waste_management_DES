"""
Cost-related configuration settings.
Contains all parameters related to operational costs, rates, and economic factors.
"""
from dataclasses import dataclass
from typing import Dict
from enum import Enum, auto
from utils.helpers import validate_config, validate_all_numeric_positive

class CostType(Enum):
    """Types of costs in the system"""
    PROCESSING = auto()
    TRANSPORTATION = auto()
    STORAGE = auto()
    ENERGY = auto()
    LANDFILL = auto()
    MAINTENANCE = auto()
    LABOR = auto()

@dataclass
class CostConfig:
    """Configuration for system costs"""
    processing_base_rate: float = 50.0  # Base processing cost per unit
    transportation_rate: float = 2.0    # Cost per unit per kilometer
    storage_rate: float = 1.0          # Cost per unit per time period
    energy_rate: float = 0.15          # Cost per kWh
    landfill_rate: float = 75.0        # Base landfill cost per unit
    maintenance_rate: float = 0.05      # Maintenance cost as percentage of processing cost
    labor_rate: float = 30.0           # Labor cost per hour

    def to_dict(self) -> Dict[CostType, float]:
        """Convert config to dictionary format"""
        return {
            CostType.PROCESSING: self.processing_base_rate,
            CostType.TRANSPORTATION: self.transportation_rate,
            CostType.STORAGE: self.storage_rate,
            CostType.ENERGY: self.energy_rate,
            CostType.LANDFILL: self.landfill_rate,
            CostType.MAINTENANCE: self.maintenance_rate,
            CostType.LABOR: self.labor_rate
        }

# Default cost configuration
DEFAULT_COST_CONFIG = CostConfig()

def _validate_cost_config_values(config: CostConfig) -> None:
    """Internal validation function for cost config values"""
    config_dict = {
        'processing_base_rate': config.processing_base_rate,
        'transportation_rate': config.transportation_rate,
        'storage_rate': config.storage_rate,
        'energy_rate': config.energy_rate,
        'landfill_rate': config.landfill_rate,
        'maintenance_rate': config.maintenance_rate,
        'labor_rate': config.labor_rate
    }
    
    # Validate all rates are positive except maintenance_rate
    validate_all_numeric_positive(config_dict, allow_zero=False, exceptions=['maintenance_rate'])
    
    # Special validation for maintenance rate (must be between 0 and 1)
    if not 0 <= config.maintenance_rate <= 1:
        raise ValueError("Maintenance rate must be between 0 and 1")

def validate_cost_config(config: CostConfig) -> None:
    """Validate cost configuration parameters"""
    validate_config(config, _validate_cost_config_values, "cost")

# Validate default configuration on import
validate_cost_config(DEFAULT_COST_CONFIG)
