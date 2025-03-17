import numpy as np
from typing import Dict, Optional
from models.enums import WasteType, RegionType, EntityStatus
from models.state import SimulationState
from models.data_classes import WasteStream, OperationalEntity
from optimization.stochastic import UncertaintySet
from core.overflow import OverflowTracker


class WasteGenerator(OperationalEntity):

    def __init__(
        self,
        env,
        name,
        waste_streams: Dict[WasteType, float],
        generation_frequency,
        storage_capacity,
        priority_level,
        environmental_impact,
        region: str,
        uncertainty_set: Optional[UncertaintySet] = None,
        initial_stock: Optional[Dict[WasteType, float]] = None,
    ):
        super().__init__()
        self.env = env
        self.name = name
        # Validate initial stock against storage capacity
        if initial_stock:
            total_initial = sum(initial_stock.values())
            if total_initial > storage_capacity:
                raise ValueError(
                    f"Initial stock ({total_initial}) exceeds storage capacity ({storage_capacity})"
                )

        # Initialize waste streams with initial stock if provided
        self.waste_streams = {
            waste_type: WasteStream(
                waste_type=waste_type,
                volume=initial_stock.get(waste_type, 0) if initial_stock else 0,
            )
            for waste_type in waste_streams.keys()
        }
        self.waste_generation_rates = waste_streams
        self.generation_frequency = generation_frequency
        self.storage_capacity = storage_capacity
        self.priority_level = priority_level
        self.uncertainty_set = uncertainty_set
        self.environmental_impact = environmental_impact
        self.current_storage = sum(initial_stock.values() if initial_stock else [0])
        self.last_collected = env.now
        # Store original region string for tracking
        self.region = region
        # Convert to enum for internal use
        # Convert region string to enum, replacing hyphen with underscore for lookup
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None

        # Initialize overflow tracker
        self.overflow_tracker = OverflowTracker()

        # Track total generation efficiently
        # Initialize total generated with initial stock
        self.total_generated = {
            waste_type: initial_stock.get(waste_type, 0.0) if initial_stock else 0.0
            for waste_type in waste_streams.keys()
        }

        # Optimize history tracking with fixed-size arrays
        self.history_size = 1000
        self.history_index = 0
        self.generation_history = {
            waste_type: {
                "times": np.zeros(self.history_size),
                "volumes": np.zeros(self.history_size),
                "totals": np.zeros(self.history_size),
                "storage": np.zeros(self.history_size),
            }
            for waste_type in waste_streams.keys()
        }

        # Pre-calculate seasonal factors for efficiency
        self.seasonal_periods = 4
        self.seasonal_factors = np.array(
            [
                1 + 0.2 * np.sin(2 * np.pi * t / self.seasonal_periods)
                for t in range(self.seasonal_periods)
            ]
        )

        # Initialize RNG with seed for reproducibility
        self.rng = np.random.default_rng(42)

        # Start waste generation process
        self.action = env.process(self.generate_waste())

    def _calculate_daily_factors(self):
        """Calculate daily generation factors based on uncertainty"""
        if not self.uncertainty_set:
            return [1.0] * len(self.waste_generation_rates)

        daily_factors = []
        for waste_type in self.waste_generation_rates.keys():
            mean, std = self.uncertainty_set.waste_generation.get(
                waste_type, (1.0, 0.2)
            )
            factor = self.rng.normal(mean, std)
            daily_factors.append(np.clip(factor, 0.1, 2.0))
        return daily_factors

    def _update_waste_stream(self, waste_type, generated_volume, current_time):
        """Update waste stream and history records"""
        self.waste_streams[waste_type].volume += generated_volume
        self.current_storage += generated_volume
        self.total_generated[waste_type] += generated_volume

        # Track waste generation in the region using original region string
        SimulationState.get_instance().track_waste_generation(
            self.region, waste_type, generated_volume
        )

        if self.history_index >= self.history_size:
            self.history_index = 0

        history = self.generation_history[waste_type]
        history["times"][self.history_index] = current_time
        history["volumes"][self.history_index] = generated_volume
        history["totals"][self.history_index] = self.total_generated[waste_type]
        history["storage"][self.history_index] = self.current_storage

    def _handle_overflow(self):
        """Handle storage overflow situation"""
        # Determine severity level
        if self.current_storage / self.storage_capacity > 0.95:
            severity = "emergency"
        elif self.current_storage / self.storage_capacity > 0.90:
            severity = "critical"
        else:
            severity = "warning"

        # Calculate overflow volume
        overflow_volume = max(0, self.current_storage - self.storage_capacity)

        # Landfill the excess waste and track it
        print(
            f"{self.env.now}: Landfilling {overflow_volume:.2f} m³ of waste from {self.name}"
        )
        self.overflow_tracker.track_overflow(
            facility_type="generator", volume=overflow_volume
        )

        # Calculate the reduction factor to bring total storage within capacity
        reduction_factor = self.storage_capacity / self.current_storage
        
        # Track waste removal from the region using original region string
        state = SimulationState.get_instance()
        total_reduced = 0.0
        
        # Proportionally reduce each waste stream
        for waste_type in self.waste_streams:
            current_volume = self.waste_streams[waste_type].volume
            reduced_volume = current_volume * (1 - reduction_factor)
            if reduced_volume > 0:
                state.track_waste_collection(self.region, waste_type, reduced_volume)
                self.waste_streams[waste_type].volume = current_volume - reduced_volume
                total_reduced += reduced_volume
        
        self.current_storage -= total_reduced

        # Calculate and apply penalty
        penalty = self.overflow_tracker.calculate_penalty(
            facility_type="generator", severity=severity, volume=overflow_volume
        )
        print(f"Overflow penalty applied to {self.name}: {penalty:.2f}")

    def _generate_waste_for_period(
        self, seasonal_factor, available_storage, current_time
    ):
        """Generate waste for all waste types in one period"""
        # Check for failure first
        if self.uncertainty_set:
            self.check_failure(current_time, self.uncertainty_set.equipment_failure_rate)

        # If failed, don't generate waste
        if self.status == EntityStatus.FAILED:
            print(f"{current_time}: Generator {self.name} is currently failed, skipping waste generation")
            return available_storage

        daily_factors = self._calculate_daily_factors()

        for (waste_type, base_rate), daily_factor in zip(
            self.waste_generation_rates.items(), daily_factors
        ):
            if available_storage <= 0:
                break

            generated_volume = min(
                base_rate * seasonal_factor * daily_factor, available_storage
            )

            if generated_volume > 0:
                self._update_waste_stream(waste_type, generated_volume, current_time)
                available_storage -= generated_volume

        return available_storage

    def generate_waste(self):
        """Generate waste with optimized calculations and failure handling"""
        while True:
            current_time = self.env.now
            
            # If we were failed but have recovered, log it
            if (self.status == EntityStatus.FAILED and 
                current_time >= self.recovery_time):
                print(f"{current_time}: Generator {self.name} has recovered from failure")
                self.status = EntityStatus.OPERATIONAL
                self.failure_time = None
                self.recovery_time = None

            season_index = int(current_time % self.seasonal_periods)
            seasonal_factor = self.seasonal_factors[season_index]

            available_storage = self.storage_capacity - self.current_storage
            if available_storage <= 0:
                self._handle_overflow()
                yield self.env.timeout(self.generation_frequency)
                continue

            self._generate_waste_for_period(
                seasonal_factor, available_storage, current_time
            )
            self.history_index += 1
            yield self.env.timeout(self.generation_frequency)

    def get_total_generated_volume(self) -> float:
        """Returns total volume across all waste streams"""
        return sum(stream.volume for stream in self.waste_streams.values())

    def get_current_waste_volumes(self) -> Dict[WasteType, float]:
        """Returns dictionary of volumes by waste type"""
        return {
            waste_type: stream.volume
            for waste_type, stream in self.waste_streams.items()
        }

    def get_generation_history_summary(self) -> Dict[str, Dict[WasteType, float]]:
        """Get efficient summary of waste generation"""
        summary = {}
        for waste_type in self.total_generated:
            history = self.generation_history[waste_type]
            valid_entries = history["volumes"][: self.history_index]

            if len(valid_entries) > 0:
                avg_volume = np.mean(valid_entries)
            else:
                avg_volume = 0

            summary[waste_type.value] = {
                "total_generated": self.total_generated[waste_type],
                "average_per_cycle": avg_volume,
                "current_storage": self.waste_streams[waste_type].volume,
                "generation_rate": self.waste_generation_rates[waste_type],
            }
        return summary

    def adjust_priority(self):
        """Adjust priority level based on storage utilization and time since last collection"""
        utilization_ratio = self.current_storage / self.storage_capacity
        time_since_collection = self.env.now - self.last_collected

        # Storage-based priority adjustment
        if utilization_ratio > 0.75:
            self.priority_level = min(10, self.priority_level + 1)
        elif utilization_ratio < 0.25:
            self.priority_level = max(1, self.priority_level - 1)

        # Time-based priority adjustment
        if time_since_collection > 5:
            self.priority_level = min(10, self.priority_level + 1)

        print(
            f"Priority for {self.name} adjusted to {self.priority_level} "
            f"due to storage utilization ({utilization_ratio:.2f}) and "
            f"time since last collection ({time_since_collection:.2f})"
        )

    def mark_collected(self):
        """Update collection status"""
        self.priority_level = max(1, self.priority_level - 1)
        self.last_collected = self.env.now
