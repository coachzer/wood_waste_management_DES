import numpy as np
from typing import Dict, Optional
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.data_classes import WasteStream, OperationalEntity
from monitoring.waste_monitor import WasteMonitor
from core.kanban_manager import KanbanManager
from core.generator_utils import (
    handle_overflow,
    generate_waste_for_period,
)

class WasteGenerator(OperationalEntity):
    def __init__(
        self,
        env,
        name,
        waste_streams: Dict[WasteType, float],
        generation_frequency,
        waste_storage_capacity,
        environmental_impact,
        region: str,
        uncertainty_set = None,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        waste_monitor: Optional[WasteMonitor] = None,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        kanban_manager=None,
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy
        # Validate initial stock against storage capacity
        if initial_stock:
            total_initial = sum(initial_stock.values())
            if total_initial > waste_storage_capacity:
                raise ValueError(
                    f"Initial stock ({total_initial}) exceeds storage capacity ({waste_storage_capacity})"
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
        self.waste_storage_capacity = waste_storage_capacity
        self.uncertainty_set = uncertainty_set
        self.environmental_impact = environmental_impact
        self.current_storage = sum(initial_stock.values() if initial_stock else [0])
        self.last_collected = env.now
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None

        self.waste_monitor = waste_monitor
        if waste_monitor is None:
            raise ValueError("waste_monitor is required for WasteGenerator")
        
        self.kanban_manager = kanban_manager or KanbanManager()

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
        print(f"DEBUG: Seasonal factors initialized: {self.seasonal_factors}")      

        # Initialize RNG with seed for reproducibility
        self.rng = np.random.default_rng(42)

        # Start waste generation process
        self.action = env.process(self.generate_waste())

    def generate_waste(self):
        """Generate waste with optimized calculations and failure handling, including Kanban pull logic"""
        while True:
            current_time = self.env.now

            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'generator_failure'):

                self.check_failure(current_time, self.uncertainty_set.generator_failure.probability)
                
                # Handle generation rate changes based on current status
                if self.status == EntityStatus.FAILED:
                    if not hasattr(self, '_original_rates'):
                        self._original_rates = self.waste_generation_rates.copy()  
                    self.waste_generation_rates = {
                        waste_type: rate * 0.1  
                        for waste_type, rate in self._original_rates.items()
                    }
                    print(f"{current_time}: Generator {self.name} is FAILED, minimal waste generation")
                    
                elif self.status == EntityStatus.RECOVERING:
                    if hasattr(self, '_original_rates'):
                        efficiency = self.get_operational_efficiency()
                        self.waste_generation_rates = {
                            waste_type: rate * efficiency  # Gradual recovery based on efficiency
                            for waste_type, rate in self._original_rates.items()
                        }
                    print(f"{current_time}: Generator {self.name} is RECOVERING (efficiency: {efficiency:.2f})")
                    
                elif self.status == EntityStatus.OPERATIONAL:
                    if hasattr(self, '_original_rates'):
                        self.waste_generation_rates = self._original_rates.copy()
                        delattr(self, '_original_rates')  # Clean up

            # Skip generation entirely only if completely failed
            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.generation_frequency)
                continue

            season_index = int(current_time % self.seasonal_periods)
            seasonal_factor = self.seasonal_factors[season_index]

            strategy = self.stock_strategy

            match strategy:
                # case StockStrategy.FULL_STOCK:
                #     self._process_full_stock(current_time, seasonal_factor)
                case StockStrategy.ON_DEMAND:
                    self._process_on_demand(current_time, seasonal_factor)
                case StockStrategy.REORDER_90:
                    self._process_reorder(current_time, seasonal_factor, 0.9, 6)
                case StockStrategy.REORDER_50:
                    self._process_reorder(current_time, seasonal_factor, 0.5, 4)

            self.history_index += 1
            yield self.env.timeout(self.generation_frequency)

    def _process_full_stock(self, current_time, seasonal_factor):
        available_storage = self.waste_storage_capacity - self.current_storage

        available_storage, self.current_storage, self.history_index = generate_waste_for_period(
            self.name, self.status, self.uncertainty_set,
            self.waste_generation_rates, self.region, self.waste_streams,
            self.total_generated, self.generation_history, self.history_index,
            self.current_storage, self.rng, seasonal_factor, available_storage,
            current_time
        )

        if self.current_storage > self.waste_storage_capacity:
            self.current_storage = handle_overflow(
                self.env, self.current_storage, self.waste_storage_capacity,
                self.waste_streams, self.region, self.waste_monitor,
                self
            )
            self._kanban_signal(current_time, 10)

    def _process_on_demand(self, current_time, seasonal_factor):
        available_storage = self.waste_storage_capacity - self.current_storage
        demand = sum(self.waste_generation_rates.values())
        
        if available_storage < demand:
            self.current_storage = handle_overflow(
                self.env, self.current_storage, self.waste_storage_capacity,
                self.waste_streams, self.region, self.waste_monitor,
                self
            )
            self._kanban_signal(current_time, 8)
        else:
            efficiency = self.get_operational_efficiency()  
            available_storage, self.current_storage, self.history_index = generate_waste_for_period(
                self.name, self.status, self.uncertainty_set,
                self.waste_generation_rates, self.region, self.waste_streams,
                self.total_generated, self.generation_history, self.history_index,
                self.current_storage, self.rng, seasonal_factor, available_storage,
                current_time, efficiency  
            )

    def _process_reorder(self, current_time, seasonal_factor, threshold_ratio, priority):
        threshold = self.waste_storage_capacity * threshold_ratio
        
        if self.current_storage >= threshold:
            # TRIGGER COLLECTION when storage is HIGH (above threshold)
            # This prevents overflow and maintains operational efficiency
            self.current_storage = handle_overflow(
                self.env, self.current_storage, self.waste_storage_capacity,
                self.waste_streams, self.region, self.waste_monitor, self
            )
            self._kanban_signal(current_time, priority)
            
            # Reduce generation rate temporarily while collection is pending
            efficiency = 0.7  # Reduced generation during high storage periods
        else:
            # NORMAL GENERATION when storage is below threshold
            efficiency = self.get_operational_efficiency()
        
        # Continue normal waste generation (waste doesn't stop being produced)
        available_storage = self.waste_storage_capacity - self.current_storage
        available_storage, self.current_storage, self.history_index = generate_waste_for_period(
            self.name, self.status, self.uncertainty_set,
            self.waste_generation_rates, self.region, self.waste_streams,
            self.total_generated, self.generation_history, self.history_index,
            self.current_storage, self.rng, seasonal_factor, available_storage,
            current_time, efficiency
        )

    def _kanban_signal(self, current_time, priority):
        for waste_type in self.waste_streams.keys():
            self.kanban_manager.add_signal(
                waste_type=waste_type,
                priority=priority,
                timestamp=current_time
            )