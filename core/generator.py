import random
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
        efficiency,
        region: str,
        uncertainty_set = None,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        waste_monitor: Optional[WasteMonitor] = None,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        kanban_manager = None,
        failure_config = None
    ):
        self.uncertainty_set = uncertainty_set

        if failure_config is None and uncertainty_set:
            failure_config = uncertainty_set.generator_failure

        super().__init__(failure_config=failure_config)
        self.env = env
        self.name = name
        self.facility_type = "generator"
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy
        if initial_stock:
            total_initial = sum(initial_stock.values())
            if total_initial > waste_storage_capacity:
                raise ValueError(
                    f"Initial stock ({total_initial}) exceeds storage capacity ({waste_storage_capacity})"
                )
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
        self.efficiency = efficiency
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

        # Initialize RNG with seed for reproducibility
        seed =  random.randint(0, 2**32 - 1)
        self.rng = np.random.default_rng(seed)

        # Start waste generation process
        self.action = env.process(self.generate_waste())

    def _handle_entity_status(self, current_time):
        """Checks for failures and updates generation rates based on entity status."""
        if self.failure_config:
            self.check_failure(current_time, self.failure_config.probability)
        else:
            raise ValueError("failure_config is required for entity status handling")

        if self.status == EntityStatus.FAILED:
            if not hasattr(self, '_original_rates'):
                self._original_rates = self.waste_generation_rates.copy()
            self.waste_generation_rates = {wt: r * 0.1 for wt, r in self._original_rates.items()}
        elif self.status == EntityStatus.RECOVERING:
            if hasattr(self, '_original_rates'):
                self.efficiency = self.get_operational_efficiency()
                self.waste_generation_rates = {wt: r * self.efficiency for wt, r in self._original_rates.items()}
        elif self.status == EntityStatus.OPERATIONAL:
            if hasattr(self, '_original_rates'):
                self.waste_generation_rates = self._original_rates.copy()
                delattr(self, '_original_rates')

    def generate_waste(self):
        """Generate waste with optimized calculations and failure handling, including Kanban pull logic"""
        while True:
            current_time = self.env.now
            self._handle_entity_status(current_time)

            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.generation_frequency)
                continue

            season_index = int(current_time % self.seasonal_periods)
            seasonal_factor = self.seasonal_factors[season_index]

            self._process_stock_strategy(current_time, seasonal_factor)

            self.history_index += 1
            yield self.env.timeout(self.generation_frequency)

    def _process_stock_strategy(self, current_time, seasonal_factor):
        """Unified strategy processing - always generate waste, manage inventory based on strategy"""

        # STEP 1: Always generate waste
        available_storage = self.waste_storage_capacity - self.current_storage

        available_storage, self.current_storage, self.history_index = generate_waste_for_period(
            self.name, self.status, self.uncertainty_set,
            self.waste_generation_rates, self.region, self.waste_streams,
            self.total_generated, self.generation_history, self.history_index,
            self.current_storage, self.rng, seasonal_factor, available_storage,
            current_time, self.efficiency
        )

        # STEP 2: Handle overflow if storage is exceeded
        if self.current_storage > self.waste_storage_capacity:
            self.current_storage = handle_overflow(
                self.current_storage,
                self.waste_storage_capacity,
                self.waste_streams,
                self.region,
                self,
                force_landfill=False,  # Try expansion first
            )

        # STEP 3: Strategy-based signaling for collection
        self._handle_inventory_signaling(current_time)

    def _handle_inventory_signaling(self, current_time):
        """Signal for collection based on stock strategy and current inventory levels"""

        match self.stock_strategy:
            case StockStrategy.REORDER_90:
                threshold = self.waste_storage_capacity * 0.9
                if self.current_storage >= threshold:
                    self._kanban_signal(current_time, priority=6)

            case StockStrategy.REORDER_50:
                threshold = self.waste_storage_capacity * 0.5
                if self.current_storage >= threshold:
                    self._kanban_signal(current_time, priority=4)

            case StockStrategy.ON_DEMAND:
                # For PULL ON_DEMAND: Only signal if we have waste AND there are active signals from downstream
                if self.inventory_policy == InventoryPolicy.PULL:
                    # Check if we have downstream demand signals
                    active_signals = self.kanban_manager.get_signals(current_time)
                    if active_signals and self.current_storage > 0:
                        self._kanban_signal(
                            current_time, priority=8
                        )  # High priority for demand response
                else:
                    # For PUSH ON_DEMAND: Signal when we have substantial waste
                    if self.current_storage > self.waste_storage_capacity * 0.1:
                        self._kanban_signal(current_time, priority=3)

    def _kanban_signal(self, current_time, priority):
        active_waste_types = [
            waste_type for waste_type, stream in self.waste_streams.items()
            if stream.volume > 0
        ]

        if active_waste_types:
            for waste_type in active_waste_types:
                self.kanban_manager.add_signal(
                    waste_type=waste_type,
                    priority=priority,
                    timestamp=current_time,
                    volume=self.waste_streams[waste_type].volume,
                    source_id=self.name,
                    source_type="generator"
                )
