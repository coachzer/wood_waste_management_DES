import numpy as np
from typing import Dict, Optional
from models.enums import WasteType, RegionType, EntityStatus
from models.data_classes import WasteStream, OperationalEntity
from core.generator_utils import (
    handle_overflow,
    generate_waste_for_period,
)

from models.enums import StockStrategy

class WasteGenerator(OperationalEntity):
    def __init__(
        self,
        env,
        name,
        waste_streams: Dict[WasteType, float],
        generation_frequency,
        storage_capacity,
        environmental_impact,
        region: str,
        uncertainty_set = None,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        data_collector = None,
        stock_strategy: StockStrategy = StockStrategy.FULL_STOCK,
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.stock_strategy = stock_strategy
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
        self.uncertainty_set = uncertainty_set
        self.environmental_impact = environmental_impact
        self.current_storage = sum(initial_stock.values() if initial_stock else [0])
        self.last_collected = env.now
        # Store original region string for tracking
        self.region = region
        # Convert to enum for internal use
        # Convert region string to enum, replacing hyphen with underscore for lookup
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None

        self.data_collector = data_collector
        if data_collector is None:
            raise ValueError("data_collector is required for WasteGenerator")

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

            # Stock strategy logic
            if self.stock_strategy == StockStrategy.FULL_STOCK:
                available_storage = self.storage_capacity - self.current_storage
                if available_storage <= 0:
                    self.current_storage = handle_overflow(
                        self.env, self.current_storage, self.storage_capacity,
                        self.waste_streams, self.region, self.data_collector
                    )
                    yield self.env.timeout(self.generation_frequency)
                    continue
                available_storage, self.current_storage, self.history_index = generate_waste_for_period(
                    self.name, self.status, self.uncertainty_set,
                    self.waste_generation_rates, self.region, self.waste_streams,
                    self.total_generated, self.generation_history, self.history_index,
                    self.current_storage, self.rng, seasonal_factor, available_storage,
                    current_time
                )
            elif self.stock_strategy == StockStrategy.ON_DEMAND:
                # Only generate what is needed, discard excess immediately
                available_storage = self.storage_capacity - self.current_storage
                demand = sum(self.waste_generation_rates.values())
                if available_storage < demand:
                    # Discard excess generation
                    self.current_storage = handle_overflow(
                        self.env, self.current_storage, self.storage_capacity,
                        self.waste_streams, self.region, self.data_collector
                    )
                else:
                    available_storage, self.current_storage, self.history_index = generate_waste_for_period(
                        self.name, self.status, self.uncertainty_set,
                        self.waste_generation_rates, self.region, self.waste_streams,
                        self.total_generated, self.generation_history, self.history_index,
                        self.current_storage, self.rng, seasonal_factor, available_storage,
                        current_time
                    )
            elif self.stock_strategy == StockStrategy.REORDER_90:
                # Trigger replenishment at 90% threshold
                if self.current_storage < self.storage_capacity * 0.9:
                    available_storage = self.storage_capacity - self.current_storage
                    available_storage, self.current_storage, self.history_index = generate_waste_for_period(
                        self.name, self.status, self.uncertainty_set,
                        self.waste_generation_rates, self.region, self.waste_streams,
                        self.total_generated, self.generation_history, self.history_index,
                        self.current_storage, self.rng, seasonal_factor, available_storage,
                        current_time
                    )
                else:
                    # Discard excess
                    self.current_storage = handle_overflow(
                        self.env, self.current_storage, self.storage_capacity,
                        self.waste_streams, self.region, self.data_collector
                    )
            elif self.stock_strategy == StockStrategy.REORDER_50:
                # Trigger replenishment at 50% threshold
                if self.current_storage < self.storage_capacity * 0.5:
                    available_storage = self.storage_capacity - self.current_storage
                    available_storage, self.current_storage, self.history_index = generate_waste_for_period(
                        self.name, self.status, self.uncertainty_set,
                        self.waste_generation_rates, self.region, self.waste_streams,
                        self.total_generated, self.generation_history, self.history_index,
                        self.current_storage, self.rng, seasonal_factor, available_storage,
                        current_time
                    )
                else:
                    # Discard excess
                    self.current_storage = handle_overflow(
                        self.env, self.current_storage, self.storage_capacity,
                        self.waste_streams, self.region, self.data_collector
                    )
            # Kanban signal handling for pull systems can be added here

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

    def mark_collected(self):
        """Update collection status"""
        self.last_collected = self.env.now
