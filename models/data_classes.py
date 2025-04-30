from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from .enums import WasteType, RegionType, EntityStatus
import random

@dataclass
class FailureConfig:
    """Configuration for entity failure rates and durations"""
    probability: float  # Hourly probability of failure
    min_duration: float  # Minimum downtime in hours
    max_duration: float  # Maximum downtime in hours
    check_interval: float = 24.0  # Hours between failure checks

@dataclass(init=False)
class OperationalEntity:
    """Base class for entities that can experience failures"""
    status: EntityStatus
    failure_time: Optional[float]
    recovery_time: Optional[float]
    downtime_duration: float
    last_failure_check: float
    failure_check_interval: float

    def __init__(self):
        """Initialize operational entity with default values"""
        self.status = EntityStatus.OPERATIONAL
        self.failure_time = None
        self.recovery_time = None
        self.downtime_duration = 24.0  # Default 24 hour recovery time
        self.last_failure_check = 0.0
        self.failure_check_interval = 24.0  # Check for failures once per day by default
    
    def check_failure(self, current_time: float, failure_probability: float) -> bool:
        """Check if entity experiences a failure"""
        # First check if enough time has passed since last check
        if current_time - self.last_failure_check < self.failure_check_interval:
            return False
            
        self.last_failure_check = current_time
        
        # If already failed, check for recovery
        if self.status == EntityStatus.FAILED:
            if current_time >= self.recovery_time:
                self.status = EntityStatus.OPERATIONAL
                self.failure_time = None
                self.recovery_time = None
                return False
            return True
            
        # Check for new failure only if operational
        if self.status == EntityStatus.OPERATIONAL and random.random() < failure_probability:
            # Scale probability by interval (since probability is typically per hour)
            scaled_probability = failure_probability * self.failure_check_interval
            if random.random() < scaled_probability:
                self.status = EntityStatus.FAILED
                self.failure_time = current_time
                self.recovery_time = current_time + self.downtime_duration
                return True
        return False

@dataclass
class CollectionResult:
    """Data class to represent results from a collection request"""
    total_collected: float
    waste_by_type: Dict[WasteType, float]


@dataclass
class WasteStream:
    """Data class to represent a waste stream"""

    waste_type: WasteType
    volume: float


@dataclass
class WasteTransformation:
    """Data class to represent a waste transformation process"""

    input_type: WasteType
    output_type: WasteType
    conversion_efficiency: float  # Percentage of input mass converted to output
    energy_required: float  # Energy required per unit mass (kWh/kg)


@dataclass
class Vehicle:
    """Data class to represent a transport vehicle"""

    id: str
    capacity: float
    current_region: RegionType
    in_transit: bool = False
    current_load: float = 0.0
    destination: Optional[RegionType] = None
    estimated_arrival: Optional[float] = None


@dataclass(init=False)
class CollectionCenter(OperationalEntity):
    """Data class to represent a waste collection center"""
    region: RegionType
    storage_capacity: float
    current_storage: Dict[WasteType, float]
    coordinates: Tuple[float, float]

    def __init__(self, region: RegionType, storage_capacity: float, 
                 current_storage: Dict[WasteType, float], coordinates: Tuple[float, float]):
        """Initialize collection center with custom downtime duration"""
        super().__init__()
        self.region = region
        self.storage_capacity = storage_capacity
        self.current_storage = current_storage
        self.coordinates = coordinates
        self.downtime_duration = 48.0  # Collection centers take longer to repair
