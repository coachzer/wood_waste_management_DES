import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
from .recording import EntityStatusRecorder
from .enums import WasteType, RegionType, EntityStatus, OutputType

@dataclass
class FailureConfig:
    """Configuration for entity failure rates and durations"""
    probability: float  # Daily probability of failure
    min_duration: float  # Minimum downtime in days
    max_duration: float  # Maximum downtime in days

@dataclass(init=False)
class OperationalEntity:
    """Base class for entities that can experience failures"""

    _failure_counts = {}
    status: EntityStatus
    failure_time: Optional[float]
    recovery_time: Optional[float]
    waste_monitor: Optional[EntityStatusRecorder]
    failure_config: Optional[FailureConfig]
    downtime_duration: float
    rng: np.random.Generator

    def __init__(self, failure_config: Optional[FailureConfig] = None, seed=None,
                 waste_monitor: Optional[EntityStatusRecorder] = None):
        """Initialize defaults; the recorder is injected, not constructed here, so
        the domain layer depends on ``EntityStatusRecorder``, not the concrete
        recorder (closes the circular import).
        """
        self.status = EntityStatus.OPERATIONAL
        self.failure_time = None
        self.recovery_time = None
        self.waste_monitor = waste_monitor
        self.failure_config = failure_config
        self.downtime_duration = 1.0
        self.rng = np.random.default_rng(seed)

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
            # Imported function-locally to avoid a config<->data_classes
            # bootstrap cycle. See tests/test_import_isolation.py.
            from config.constants import RECOVERING_BASE_EFFICIENCY
            return RECOVERING_BASE_EFFICIENCY + ((1.0 - RECOVERING_BASE_EFFICIENCY) * self.recovery_progress)
        else:
            return 0.0

    def _get_recovery_duration(self):
        """Get random recovery duration based on failure config"""
        if self.failure_config:
            return self.rng.uniform(
                self.failure_config.min_duration,
                self.failure_config.max_duration
            )
        return 1.0

@dataclass
class WasteStream:
    """Data class to represent a waste stream"""

    waste_type: WasteType
    volume: float

@dataclass
class WasteTransformation:
    """Data class to represent a waste transformation process"""

    input_type: WasteType
    output_type: OutputType
    conversion_efficiency: float  # Percentage of input mass converted to output
    energy_required: float  # Energy required per unit mass (kWh/kg)

@dataclass
class Vehicle:
    """Data class to represent a transport vehicle"""
    id: str
    capacity: float  # Storage capacity in m³
    current_region: RegionType
    in_transit: bool = False
    current_load: float = 0.0  # Current load in m³ (total across waste types)
    # Per-waste-type breakdown of current_load (m³); sums to current_load. Read by
    # the waste-side mass-balance invariant to total waste in transit by type.
    current_load_by_type: Dict[WasteType, float] = field(default_factory=dict)
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
        from config.constants import COLLECTION_CENTER_DOWNTIME_DAYS
        self.downtime_duration = COLLECTION_CENTER_DOWNTIME_DAYS

@dataclass
class ProductStorage:
    """Data class to represent storage for finished products"""
    capacity: Dict[OutputType, float]  # Capacity in m³ per product type (ADR 0002, Phase C)
    current_storage: Dict[OutputType, float] # Current storage in m³ per product type

@dataclass
class ABCClassification:
    """ABC classification result for a product"""
    product_type: str
    biogenic_carbon_per_unit: float  # kg CO2eq/m3
    demand_volume: float  # m3
    total_biogenic_impact: float  # Total kg CO2eq
    abc_class: str
    cumulative_percentage: float
    priority_weight: float
