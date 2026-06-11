import numpy as np
from typing import Dict, Optional
from config.constants import HISTORY_BUFFER_SIZE
from utils.seasonality import seasonal_factor
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.data_classes import WasteStream, OperationalEntity
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
        environmental_impact,
        efficiency,
        region: str,
        uncertainty_set = None,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        waste_monitor: Optional[WasteMonitor] = None,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        kanban_manager = None,
        state = None,
        failure_config = None,
        seed = None
    ):
        self.uncertainty_set = uncertainty_set

        if failure_config is None and uncertainty_set:
            failure_config = uncertainty_set.generator_failure

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
        if uncertainty_set and uncertainty_set.waste_generation_mean != 1.0:
            mean_multiplier = uncertainty_set.waste_generation_mean
            self.waste_generation_rates = {
                waste_type: rate * mean_multiplier
                for waste_type, rate in self.waste_generation_rates.items()
            }
        self.generation_frequency = generation_frequency
        self.waste_storage_capacity = waste_storage_capacity
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
        self.state = state

        self.total_generated = {
            waste_type: initial_stock.get(waste_type, 0.0) if initial_stock else 0.0
            for waste_type in waste_streams.keys()
        }

        # Potential (pre-saturation) generation: the volume the exogenous source
        # offered each tick before the storage-headroom cap, policy-invariant and
        # the basis for the bullwhip source-variance floor (ADR 0005). Mirrors
        # total_generated's keys and initial-stock baseline.
        self.total_potential_generated = dict(self.total_generated)

        self.history_size = HISTORY_BUFFER_SIZE
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

        # Start waste generation process
        self.action = env.process(self.generate_waste())

    def _apply_status_throughput_effects(self):
        """Scale generation rates by status, restoring originals on recovery."""
        if self.status == EntityStatus.FAILED:
            if not hasattr(self, '_original_rates'):
                self._original_rates = self.waste_generation_rates.copy()
            self.waste_generation_rates = {wt: r * self.get_operational_efficiency() for wt, r in self._original_rates.items()}
        elif self.status == EntityStatus.RECOVERING:
            if hasattr(self, '_original_rates'):
                self.efficiency = self.get_operational_efficiency()
                self.waste_generation_rates = {wt: r * self.efficiency for wt, r in self._original_rates.items()}
        elif self.status == EntityStatus.OPERATIONAL:
            if hasattr(self, '_original_rates'):
                self.efficiency = 1.0
                self.waste_generation_rates = self._original_rates.copy()
                delattr(self, '_original_rates')

    def generate_waste(self):
        """Generate waste with optimized calculations and failure handling, including Kanban pull logic"""
        while True:
            current_time = self.env.now

            if self.apply_failure_tick(current_time):
                yield self.env.timeout(self.generation_frequency)
                continue

            self._process_stock_strategy(current_time, seasonal_factor(current_time))

            self.history_index += 1
            yield self.env.timeout(self.generation_frequency)

    def _process_stock_strategy(self, current_time, seasonal_factor):
        """Unified strategy processing - always generate waste, manage inventory based on strategy"""

        self._generate_waste_for_period(seasonal_factor, current_time)

        if self.current_storage > self.waste_storage_capacity:
            self._handle_overflow(force_landfill=False)  # try expansion first

        self._handle_inventory_signaling(current_time)

    def _handle_inventory_signaling(self, current_time):
        """Signal for collection based on stock strategy and current inventory levels"""

        # The downstream-signal read is wrapped in a callable because
        # ``get_signals`` prunes stale signals as a side effect: only the
        # PULL ON_DEMAND branch consulted it, so it must not fire on the others.
        if self.stock_strategy_behavior.generator_should_signal(
            current_storage=self.current_storage,
            capacity=self.waste_storage_capacity,
            inventory_policy=self.inventory_policy_behavior,
            active_signals_fn=lambda: self.kanban_manager.get_signals(current_time),
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
        if not self.uncertainty_set:
            return [1.0] * len(self.waste_generation_rates)

        daily_factors = []
        variability = getattr(self.uncertainty_set, 'waste_generation_variability', 0.2)

        for _ in self.waste_generation_rates.keys():
            factor = self.rng.normal(1.0, variability)
            daily_factors.append(np.clip(factor, 0.1, 2.0))
        return daily_factors

    def _update_waste_stream(self, waste_type, generated_volume, current_time, history_index):
        """Update waste stream and history records"""
        history = self.generation_history[waste_type]

        self.waste_streams[waste_type].volume += generated_volume
        self.current_storage += generated_volume
        self.total_generated[waste_type] += generated_volume

        self.state.track_add_waste(
            self.region, waste_type, generated_volume
        )

        if history_index >= len(history["times"]):
            history_index = 0

        history["times"][history_index] = current_time
        history["volumes"][history_index] = generated_volume
        history["totals"][history_index] = self.total_generated[waste_type]
        history["storage"][history_index] = self.current_storage

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

            # Capacity may have expanded inside handle_storage_event; read it fresh
            effective_capacity = self.waste_storage_capacity

            if total_current > effective_capacity:
                scaling_factor = effective_capacity / total_current

                state = self.state

                for waste_type, stream in self.waste_streams.items():
                    new_volume = stream.volume * scaling_factor
                    reduced_volume = stream.volume - new_volume
                    if reduced_volume > 0:
                        state.track_remove_waste(self.region, waste_type, reduced_volume)
                        stream.volume = new_volume

                self.current_storage = effective_capacity
            else:
                self.current_storage = total_current

    def _generate_waste_for_period(self, seasonal_factor, current_time):
        """Generate waste for all waste types in one period with efficiency consideration"""
        if self.uncertainty_set:
            if self.status == EntityStatus.FAILED:
                return

        available_storage = self.waste_storage_capacity - self.current_storage
        daily_factors = self._calculate_daily_factors()

        for (waste_type, base_rate), daily_factor in zip(
            self.waste_generation_rates.items(), daily_factors
        ):
            potential_volume = base_rate * seasonal_factor * daily_factor * self.efficiency

            # Record the source-offered volume before the storage cap (ADR 0005
            # floor), accumulated for every waste type and consuming no RNG.
            self.total_potential_generated[waste_type] += potential_volume

            generated_volume = min(potential_volume, available_storage)
            if generated_volume > 0:
                self._update_waste_stream(
                    waste_type, generated_volume, current_time, self.history_index
                )
                available_storage -= generated_volume
