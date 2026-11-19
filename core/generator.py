import numpy as np
from typing import Dict, List, Optional
from utils.seasonality import seasonal_factor
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.data_classes import FailureConfig, WasteStream, OperationalEntity
from config.base_config import ScenarioConfig
from instrumentation.waste_monitor import WasteMonitor
from core.kanban_manager import KanbanManager
from core.strategies import build_stock_strategy, build_inventory_policy
from utils.capacity_utils import handle_storage_event, split_overflow_by_type

class WasteGenerator(OperationalEntity):
    def __init__(
        self,
        env,
        name,
        waste_streams: Dict[WasteType, float],
        generation_frequency,
        waste_storage_capacity,
        efficiency,
        region_type: RegionType,
        scenario: ScenarioConfig,
        waste_monitor: WasteMonitor,
        stock_strategy: StockStrategy,
        inventory_policy: InventoryPolicy,
        kanban_manager: KanbanManager,
        state,
        failure_config: Optional[FailureConfig],
        seed,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        accepted_waste_types: Optional[List[WasteType]] = None,
    ):
        self.scenario = scenario
        super().__init__(failure_config=failure_config, seed=seed)
        self.env = env
        self.name = name
        self.facility_type = "generator"
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy
        self.stock_strategy_behavior = build_stock_strategy(stock_strategy)
        self.inventory_policy_behavior = build_inventory_policy(inventory_policy)
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
        self.waste_generation_rates = dict(waste_streams)
        if scenario.waste_generation_mean != 1.0:
            mean_multiplier = scenario.waste_generation_mean
            self.waste_generation_rates = {
                waste_type: rate * mean_multiplier
                for waste_type, rate in self.waste_generation_rates.items()
            }
        self.generation_frequency = generation_frequency
        self.waste_storage_capacity = waste_storage_capacity
        self.efficiency = efficiency
        self.current_storage = sum(initial_stock.values() if initial_stock else [0])
        self.region_type = region_type
        self.waste_monitor = waste_monitor
        self.kanban_manager = kanban_manager
        self.state = state

        self.total_generated = {
            waste_type: initial_stock.get(waste_type, 0.0) if initial_stock else 0.0
            for waste_type in waste_streams.keys()
        }

        self.total_potential_generated = dict(self.total_generated)
        self.total_uncollected = {waste_type: 0.0 for waste_type in waste_streams.keys()}
        self.outlet_waste_types = frozenset(
            waste_type for waste_type in waste_streams
            if accepted_waste_types is not None and waste_type not in accepted_waste_types
        )
        self.total_outlet = {waste_type: 0.0 for waste_type in waste_streams.keys()}
        self._in_failure_cycle = False

        self.action = env.process(self.generate_waste())
        self.start_failure_process(env)

    def _apply_status_throughput_effects(self):
        """Carry a failure on efficiency alone; generation multiplies the rates by it once."""
        if self.status == EntityStatus.FAILED:
            self._in_failure_cycle = True
        elif self.status == EntityStatus.RECOVERING:
            if self._in_failure_cycle:
                self.efficiency = self.get_operational_efficiency()
        elif self.status == EntityStatus.OPERATIONAL:
            if self._in_failure_cycle:
                self.efficiency = 1.0
                self._in_failure_cycle = False

    def generate_waste(self):
        """Generate waste with optimized calculations and failure handling, including Kanban pull logic"""
        while True:
            current_time = self.env.now

            if self.apply_failure_tick():
                yield self.env.timeout(self.generation_frequency)
                continue

            self._process_stock_strategy(current_time, seasonal_factor(current_time))

            yield self.env.timeout(self.generation_frequency)

    def _process_stock_strategy(self, current_time, seasonal_factor):
        """Unified strategy processing - always generate waste, manage inventory based on strategy"""

        self._generate_waste_for_period(seasonal_factor)

        if self.current_storage > self.waste_storage_capacity:
            self._handle_overflow(force_landfill=False)

        self._handle_inventory_signaling(current_time)

    def _handle_inventory_signaling(self, current_time):
        """Signal for collection based on stock strategy and current inventory levels"""
        if not self.inventory_policy_behavior.generators_request_pickup():
            return

        if self.stock_strategy_behavior.generator_should_signal(
            current_storage=self.current_storage,
            capacity=self.waste_storage_capacity,
            inventory_policy=self.inventory_policy_behavior,
        ):
            self._kanban_signal(current_time)

    def _kanban_signal(self, current_time):
        active_waste_types = [
            waste_type for waste_type, stream in self.waste_streams.items()
            if stream.volume > 0
        ]

        if active_waste_types:
            for waste_type in active_waste_types:
                self.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=self.waste_streams[waste_type].volume,
                    source_id=self.name,
                    source_type="generator"
                )

    def _calculate_daily_factors(self):
        """Calculate daily generation factors based on uncertainty"""
        daily_factors = []
        variability = self.scenario.waste_generation_variability

        for _ in self.waste_generation_rates.keys():
            factor = self.rng.normal(1.0, variability)
            daily_factors.append(np.clip(factor, 0.1, 2.0))
        return daily_factors

    def _update_waste_stream(self, waste_type, generated_volume):
        self.waste_streams[waste_type].volume += generated_volume
        self.current_storage += generated_volume
        self.total_generated[waste_type] += generated_volume

    def _handle_overflow(self, force_landfill=False):
        """Handle storage overflow situation"""
        current_volumes = {
            waste_type: stream.volume
            for waste_type, stream in self.waste_streams.items()
        }

        total_current = sum(current_volumes.values())
        if total_current > self.waste_storage_capacity:
            overflow_amount = total_current - self.waste_storage_capacity

            handle_storage_event(
                self,
                split_overflow_by_type(current_volumes, overflow_amount),
                force_landfill=force_landfill
            )

            effective_capacity = self.waste_storage_capacity

            if total_current > effective_capacity:
                scaling_factor = effective_capacity / total_current

                for waste_type, stream in self.waste_streams.items():
                    stream.volume *= scaling_factor

                self.current_storage = effective_capacity
            else:
                self.current_storage = total_current

    def _generate_waste_for_period(self, seasonal_factor):
        """Generate waste for all waste types in one period with efficiency consideration"""
        available_storage = self.waste_storage_capacity - self.current_storage
        daily_factors = self._calculate_daily_factors()

        for (waste_type, base_rate), daily_factor in zip(
            self.waste_generation_rates.items(), daily_factors
        ):
            potential_volume = base_rate * seasonal_factor * daily_factor * self.efficiency

            self.total_potential_generated[waste_type] += potential_volume

            if waste_type in self.outlet_waste_types:
                self.total_outlet[waste_type] += potential_volume
                continue

            generated_volume = max(0.0, min(potential_volume, available_storage))
            self.total_uncollected[waste_type] += potential_volume - generated_volume
            if generated_volume > 0:
                self._update_waste_stream(waste_type, generated_volume)
                available_storage -= generated_volume
