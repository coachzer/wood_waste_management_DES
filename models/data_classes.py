import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
from config.constants import (
    COLLECTION_CENTER_DOWNTIME_DAYS,
    FAILURE_CHECK_INTERVAL_DAYS,
    RECOVERING_BASE_EFFICIENCY,
)
from .recording import EntityStatusRecorder
from .enums import WasteType, RegionType, EntityStatus, OutputType
from .units import (
    CubicMetres,
    DailyProbability,
    Days,
    Fraction,
    KilogramsCO2e,
    KilogramsCO2ePerCubicMetre,
    KilowattHoursPerKilogram,
)

@dataclass
class FailureConfig:
    """Configuration for entity failure rates and durations.

    The duration bounds apply separately to the FAILED outage and to the RECOVERING ramp.
    """
    probability: DailyProbability
    min_duration: Days
    max_duration: Days

@dataclass(init=False)
class OperationalEntity:
    """Base class for entities that can experience failures"""

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
        self.failure_count = 0
        self.failure_time = None
        self.recovery_time = None
        self.waste_monitor = waste_monitor
        self.failure_config = failure_config
        self.downtime_duration = 1.0
        self.rng = np.random.default_rng(seed)
        seed_sequence = seed if isinstance(seed, np.random.SeedSequence) else np.random.SeedSequence(seed)
        [failure_seed] = seed_sequence.spawn(1)
        self.policy_independent_failure_rng = np.random.default_rng(failure_seed)

    def start_failure_process(self, env) -> None:
        """Start the daily failure clock when the entity has a failure_config.

        Failures run on their own SimPy process, decoupled from the entity's
        main loop, so ``FailureConfig.probability`` is a true daily rate whatever
        the loop cadence. The main loop only reads the resulting status.
        """
        if self.failure_config:
            env.process(self._failure_process(env))

    def _failure_process(self, env):
        """Advance the failure state machine once per FAILURE_CHECK_INTERVAL_DAYS."""
        while True:
            yield env.timeout(FAILURE_CHECK_INTERVAL_DAYS)
            self.check_failure(env.now, self.failure_config.probability)

    def check_failure(self, current_time, failure_probability):
        """Advance OPERATIONAL -> FAILED -> RECOVERING -> OPERATIONAL by one step.

        On failure the outage length is drawn from the failure_config, so FAILED
        lasts ``uniform(min_duration, max_duration)`` days (resolved at the
        daily check granularity), followed by a RECOVERING ramp of a second
        independent draw from the same range.
        """

        if self.status == EntityStatus.OPERATIONAL:
            if self.policy_independent_failure_rng.random() < failure_probability:
                self.failure_count += 1

                self.status = EntityStatus.FAILED
                self.failure_start_time = current_time
                self.downtime_duration = self._get_recovery_duration()

                if hasattr(self, 'waste_monitor') and self.waste_monitor:
                    self.waste_monitor.record_entity_status(self, current_time)

                print(f"FAILURE: {self.__class__.__name__} {getattr(self, 'name', 'unknown')} failed at time {current_time}")
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

    def apply_failure_tick(self) -> bool:
        """Apply the current failure status to one tick of the entity's main loop.

        The status itself is advanced by the daily failure process
        (``start_failure_process``); this applies the entity's status-driven
        throughput effects and returns True when the caller should skip this
        tick's work because the entity is FAILED (a failed entity does no work).
        """
        self._apply_status_throughput_effects()
        return self.status == EntityStatus.FAILED

    def _apply_status_throughput_effects(self):
        """Map the current failure status onto entity throughput state.

        Subclasses override to scale whatever drives their output (collector
        efficiency, treatment processing capacity, generator rates); the base
        entity has no throughput state to adjust.
        """

    def get_operational_efficiency(self) -> float:
        """Get current operational efficiency based on status"""
        if self.status == EntityStatus.OPERATIONAL:
            return 1.0
        elif self.status == EntityStatus.RECOVERING:
            return RECOVERING_BASE_EFFICIENCY + ((1.0 - RECOVERING_BASE_EFFICIENCY) * self.recovery_progress)
        else:
            return 0.0

    def _get_recovery_duration(self):
        """Draw an outage or recovery-ramp duration from the failure config."""
        if self.failure_config:
            return self.policy_independent_failure_rng.uniform(
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
    conversion_efficiency: Fraction
    energy_required: KilowattHoursPerKilogram

@dataclass
class Vehicle:
    """Data class to represent a transport vehicle"""
    id: str
    capacity: CubicMetres
    current_region: RegionType
    in_transit: bool = False
    current_load: CubicMetres = 0.0
    current_load_by_type: Dict[WasteType, CubicMetres] = field(default_factory=dict)
    destination: Optional[RegionType] = None
    estimated_arrival: Optional[float] = None

@dataclass(init=False)
class CollectionCenter(OperationalEntity):
    """Data class to represent a waste collection center"""
    region: RegionType
    waste_storage_capacity: CubicMetres
    current_storage: Dict[WasteType, CubicMetres]
    coordinates: Tuple[float, float]

    def __init__(self, region: RegionType, waste_storage_capacity: float,
                 current_storage: Dict[WasteType, float], coordinates: Tuple[float, float]):
        """Initialize collection center with custom downtime duration"""
        super().__init__()
        self.region = region
        self.waste_storage_capacity = waste_storage_capacity
        self.current_storage = current_storage
        self.coordinates = coordinates
        self.downtime_duration = COLLECTION_CENTER_DOWNTIME_DAYS

@dataclass
class ProductStorage:
    """Data class to represent storage for finished products"""
    capacity: Dict[OutputType, CubicMetres]
    current_storage: Dict[OutputType, CubicMetres]

@dataclass
class ABCClassification:
    """ABC classification result for a product"""
    product_type: str
    biogenic_carbon_per_unit: KilogramsCO2ePerCubicMetre
    demand_volume: CubicMetres
    total_biogenic_impact: KilogramsCO2e
    abc_class: str
    cumulative_percentage: float
    priority_weight: float
