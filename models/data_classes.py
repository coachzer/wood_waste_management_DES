import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from monitoring.waste_monitor import WasteMonitor
from .enums import WasteType, RegionType, EntityStatus, OutputType

@dataclass
class FailureConfig:
    """Configuration for entity failure rates and durations"""
    probability: float  # Daily probability of failure
    min_duration: float  # Minimum downtime in days
    max_duration: float  # Maximum downtime in days
    check_interval: float = 1.0  # Daily between failure checks

@dataclass(init=False)
class OperationalEntity:
    """Base class for entities that can experience failures"""

    _entity_registry = {}
    _failure_counts = {}
    status: EntityStatus
    failure_time: Optional[float]
    recovery_time: Optional[float]
    waste_monitor: WasteMonitor
    downtime_duration: float
    last_failure_check: float
    failure_check_interval: float
    rng: np.random.Generator  

    def __init__(self):
        """Initialize operational entity with default values"""
        self.status = EntityStatus.OPERATIONAL
        self.failure_time = None
        self.recovery_time = None
        self.waste_monitor = WasteMonitor()
        self.downtime_duration = 24.0  
        self.last_failure_check = 0.0
        self.failure_check_interval = 1.0  
        self.rng = np.random.default_rng(42) 

    @classmethod
    def get_entity_counts(cls):
        """Get count of each entity type"""
        return {entity_type: len(entities) 
                for entity_type, entities in cls._entity_registry.items()}
    
    @classmethod
    def get_failure_stats(cls):
        """Get failure statistics"""
        return cls._failure_counts.copy()
    
    def check_failure(self, current_time, failure_probability):
        """Enhanced failure checking with recovery state management"""

        if self.status == EntityStatus.OPERATIONAL:
            if self.rng.random() < failure_probability:
                entity_type = self.__class__.__name__
                if entity_type not in self._failure_counts:
                    self._failure_counts[entity_type] = 0
                self._failure_counts[entity_type] += 1
                
                self.status = EntityStatus.FAILED
                self.failure_start_time = current_time

                if hasattr(self, 'waste_monitor') and self.waste_monitor:
                    self.waste_monitor.record_entity_status(self, current_time)

                print(f"FAILURE: {entity_type} {getattr(self, 'name', 'unknown')} failed at time {current_time}")
                return True
                
        elif self.status == EntityStatus.FAILED:
            if current_time - self.failure_start_time >= self.downtime_duration:
                self.status = EntityStatus.RECOVERING
                self.recovery_start_time = current_time
                self.recovery_duration = self._get_recovery_duration()
                self.recovery_progress = 0.0

                if hasattr(self, 'waste_monitor') and self.waste_monitor:
                    self.waste_monitor.record_entity_status(self, current_time)
                
        elif self.status == EntityStatus.RECOVERING:
            elapsed = current_time - self.recovery_start_time
            self.recovery_progress = min(1.0, elapsed / self.recovery_duration)
            
            if self.recovery_progress >= 1.0:
                self.status = EntityStatus.OPERATIONAL
                if hasattr(self, 'waste_monitor') and self.waste_monitor:
                    self.waste_monitor.record_entity_status(self, current_time)
                self.recovery_start_time = None
                self.recovery_duration = None
                self.recovery_progress = 0.0
                
        return self.status == EntityStatus.FAILED
    
    def get_operational_efficiency(self) -> float:
        """Get current operational efficiency based on status"""
        if self.status == EntityStatus.OPERATIONAL:
            return 1.0
        elif self.status == EntityStatus.RECOVERING:
            return 0.3 + (0.7 * self.recovery_progress)
        else: 
            return 0.0

    def _get_recovery_duration(self):
        """Override in subclasses for entity-specific recovery times"""
        return self.downtime_duration
    
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
    capacity: float  # Storage capacity in m³
    current_region: RegionType
    in_transit: bool = False
    current_load: float = 0.0  # Current load in m³
    destination: Optional[RegionType] = None
    estimated_arrival: Optional[float] = None

@dataclass(init=False)
class CollectionCenter(OperationalEntity):
    """Data class to represent a waste collection center"""
    region: RegionType
    waste_storage_capacity: float # Storage capacity in m³
    current_storage: Dict[WasteType, float] # Current storage in m³ per waste type
    coordinates: Tuple[float, float]

    def __init__(self, region: RegionType, waste_storage_capacity: float, 
                 current_storage: Dict[WasteType, float], coordinates: Tuple[float, float]):
        """Initialize collection center with custom downtime duration"""
        super().__init__()
        self.region = region
        self.waste_storage_capacity = waste_storage_capacity
        self.current_storage = current_storage
        self.coordinates = coordinates
        self.downtime_duration = 48.0  # Collection centers take longer to repair

@dataclass
class ProductStorage:
    """Data class to represent storage for finished products"""
    capacity: float
    current_storage: Dict[OutputType, float] # Current storage in m³ per product type
    densities: Optional[Dict[OutputType, float]] = None  # e.g., kg/m3 per product
