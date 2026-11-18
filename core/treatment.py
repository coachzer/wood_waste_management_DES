import logging

import numpy as np
from typing import Dict, List, Optional
from core.abc_analysis import BiogenicCarbonABCAnalyzer
from models.data_classes import WasteTransformation, OperationalEntity, ProductStorage
from models.distances import get_distance
from models.enums import OutputType, RegionType, StockStrategy, WasteType, EntityStatus
from instrumentation.waste_monitor import WasteMonitor
from core.kanban_manager import KanbanManager
from core.strategies import build_stock_strategy, build_inventory_policy
from models.enums import InventoryPolicy
from models.transformations import TRANSFORMATION_CATALOGUE, WASTE_TO_OUTPUT_TYPES
from utils.capacity_utils import (
    handle_storage_event,
    check_storage_capacity,
    compute_and_handle_overflow,
    split_overflow_by_type,
)
from config.constants import (
    INITIAL_INVENTORY_FRACTION,
    PROCESSING_CAPACITY_FRACTION,
    CARBON_PRICE_EUR_PER_KG_CO2E,
    ABC_PRIORITY_SCORE_MULTIPLIER,
    INPUT_AVAILABILITY_SATURATION_M3,
    OPERATING_TICK_DAYS,
)
from utils.capacity_utils import per_tick_capacity

class TreatmentOperator(OperationalEntity):
    """Treatment operator that processes waste into products"""

    def __init__(
        self,
        env,
        name,
        processing_time,
        waste_storage_capacity,
        energy_consumption,
        environmental_impact,
        operational_costs,
        region: str,
        uncertainty_set=None,
        transformations: Optional[Dict[WasteType, WasteTransformation]] = None,
        waste_monitor: Optional[WasteMonitor] = None,
        kanban_manager: KanbanManager = None,
        finished_goods_capacity: Optional[Dict[OutputType, float]] = None,
        initial_waste_storage: Optional[Dict[WasteType, float]] = None,
        order_share_by_waste_type: Optional[Dict[WasteType, float]] = None,
        order_up_to_level_m3: Optional[float] = None,
        market_share: float = 0.0,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        state = None,
        abc_demand_config_path: str = "data/demand.json",
        failure_config = None,
        seed = None
    ):
        self.uncertainty_set = uncertainty_set

        if failure_config is None and uncertainty_set:
            failure_config = uncertainty_set.treatment_failure

        super().__init__(failure_config=failure_config, seed=seed)

        self.waste_monitor = waste_monitor
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy

        if waste_monitor is None:
            raise ValueError("waste_monitor is required for TreatmentOperator")
        if self.inventory_policy is None:
            raise ValueError("inventory_policy must be provided")
        if self.stock_strategy is None:
            raise ValueError("stock_strategy must be provided")

        self.stock_strategy_behavior = build_stock_strategy(stock_strategy)
        self.inventory_policy_behavior = build_inventory_policy(inventory_policy)

        self.kanban_manager = kanban_manager or KanbanManager()
        self.state = state
        self.env = env
        self.name = name
        self.facility_type = "treatment"
        self.processing_time = processing_time
        self.waste_storage_capacity = waste_storage_capacity
        self.energy_consumption = energy_consumption
        self.operational_costs = operational_costs
        self.environmental_impact = environmental_impact
        self.processing_capacity_per_tick_m3 = per_tick_capacity(
            self.waste_storage_capacity * PROCESSING_CAPACITY_FRACTION, self.processing_time
        )
        self.initial_processing_capacity_per_tick_m3 = self.processing_capacity_per_tick_m3
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')]
        self.market_share = market_share
        if order_share_by_waste_type is None:
            raise ValueError("order_share_by_waste_type is required for TreatmentOperator (ADR 0026)")
        self.order_share_by_waste_type = dict(order_share_by_waste_type)
        if order_up_to_level_m3 is None:
            raise ValueError("order_up_to_level_m3 is required for TreatmentOperator (ADR 0027)")
        self.order_up_to_level_m3 = order_up_to_level_m3
        self._waste_storage = dict.fromkeys(WasteType, 0.0)
        if initial_waste_storage:
            for waste_type, volume in initial_waste_storage.items():
                self._waste_storage[waste_type] = volume
        self.processed_volumes = dict.fromkeys(WasteType, 0.0)
        self.product_volumes = {
            "mdf": 0.0,
            "particle_board": 0.0,
            "osb": 0.0
        }
        self.expected_output_volume_from_intake_m3 = 0.0
        finished_goods_capacity = finished_goods_capacity or {}
        self.finished_goods = ProductStorage(
            capacity=finished_goods_capacity,
            current_storage={
                output_type: INITIAL_INVENTORY_FRACTION * finished_goods_capacity.get(output_type, 0.0)
                for output_type in OutputType
            }
        )
        self.pull_production_backlog_m3_by_product: Dict[str, float] = {
            output_type.value: finished_goods_capacity.get(output_type, 0.0)
            - self.finished_goods.current_storage[output_type]
            for output_type in sorted(OutputType, key=lambda output_type: output_type.value)
        }

        self.transformations = transformations or self._default_transformations()

        self.abc_priority_map = {}
        self._initialize_abc_priorities(abc_demand_config_path)

        self.process = env.process(self.run_facility())
        env.process(self.schedule_collection_requests())
        self.start_failure_process(env)

    @property
    def current_storage(self) -> float:
        """Get total current storage across all waste types"""
        return sum(self.waste_storage.values())

    @property
    def storage_utilization(self) -> float:
        """Get current storage utilization as a percentage"""
        return (
            (self.current_storage / self.waste_storage_capacity) * 100
            if self.waste_storage_capacity > 0
            else 0.0
        )

    @property
    def waste_storage(self) -> Dict[WasteType, float]:
        """Get the waste storage dictionary"""
        return self._waste_storage

    @waste_storage.setter
    def waste_storage(self, new_storage: Dict[WasteType, float]):
        """Set waste storage with overflow detection"""
        if not isinstance(new_storage, dict):
            return

        total_new = sum(new_storage.values())
        if total_new > self.waste_storage_capacity:
            overflow_amount = total_new - self.waste_storage_capacity
            handle_storage_event(
                self,
                split_overflow_by_type(new_storage, overflow_amount)
            )

            scaling_factor = self.waste_storage_capacity / total_new
            self._waste_storage = {
                waste_type: amount * scaling_factor
                for waste_type, amount in new_storage.items()
            }
        else:
            self._waste_storage = dict(new_storage)

    def _initialize_abc_priorities(self, config_path: str):
        """Initialize ABC priorities - reuse existing ABCAnalyzer.

        Raises on a missing or malformed demand config rather than falling
        back to hardcoded weights: the fallback would silently change what
        every operator produces while looking like a configured run.
        """
        analyzer = BiogenicCarbonABCAnalyzer(config_path)
        classifications = analyzer.perform_abc_classification()

        self.abc_priority_map = {
            item.product_type: item.priority_weight
            for item in classifications
        }

    def _order_volumes_by_waste_type(self) -> Dict[WasteType, float]:
        """Multi-item (s, S) order: one order-up-to level per input type (ADR 0026).

        A type's level is its share of ``order_up_to_level_m3`` (ADR 0027). It reorders when
        its on-hand stock is below the strategy fraction of its level (ON_DEMAND:
        any shortfall, so the order is lot-for-lot) and orders the gap to its
        level. An empty result means no order this tick. Inventory position is
        on-hand stock: intake is drained from collectors within the tick, so
        nothing ordered is still on the way.
        """
        orders = {}
        for waste_type in sorted(self.order_share_by_waste_type, key=lambda waste_type: waste_type.value):
            level = self.order_up_to_level_m3 * self.order_share_by_waste_type[waste_type]
            on_hand = self.waste_storage.get(waste_type, 0.0)
            if self.stock_strategy_behavior.treatment_should_reorder(on_hand, level) and level > on_hand:
                orders[waste_type] = level - on_hand
        return orders

    def schedule_collection_requests(self):
        """Strategy-aware (s, S) collection polling (ADR 0002, signal-volume rule).

        Triggers when waste storage drops below the strategy threshold ``s`` and
        orders the (s, S) signal volume (gap to full capacity), detached from the
        legacy ``unmet_demands`` ceiling. PULL additionally cascades the demand
        upstream through the kanban signals before collecting -- the one
        behavioral difference between the policies, which the policy owns.
        """
        while True:
            current_time = self.env.now

            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(OPERATING_TICK_DAYS)
                continue

            order_volumes = self._order_volumes_by_waste_type()
            if order_volumes:
                if self.inventory_policy_behavior.propagates_reorder_signals_upstream():
                    self._create_reorder_signals(order_volumes, current_time)
                self.trigger_collection(order_volumes)

            yield self.env.timeout(OPERATING_TICK_DAYS)

    def _create_collection_signal(
        self, waste_type: WasteType, volume: float, timestamp: float
    ):
        """Create a collection signal for specific waste type and volume."""
        self._propagate_signal_to_collectors(waste_type, volume, timestamp)

    def _create_reorder_signals(self, order_volumes: Dict[WasteType, float], timestamp: float):
        """Post one reorder signal per ordered waste type, for that type's order volume."""
        for waste_type in sorted(order_volumes, key=lambda waste_type: waste_type.value):
            self._create_collection_signal(waste_type, order_volumes[waste_type], timestamp)

    def _propagate_signal_to_collectors(self, waste_type, needed_volume, current_time):
        """Propagate signals to collectors with availability checking"""
        state = self.state

        local_collectors = [
            c for c in state.collectors
            if (c.region_type == self.region_type and
                c.inventory_policy.is_pull() and
                c.availability)
        ]

        for collector in local_collectors:
            if needed_volume > 0:
                collector.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=needed_volume,
                    source_id=self.name,
                    source_type="treatment",
                    target_region=self.region_type,
                )

        local_stock = sum(c.collection_center.current_storage.get(waste_type, 0.0) for c in local_collectors) + sum(
            g.waste_streams[waste_type].volume
            for g in state.generators
            if g.region_type == self.region_type and waste_type in g.waste_streams
        )
        deficit = needed_volume - local_stock
        surplus_region = self._region_with_largest_generator_stock(waste_type)
        if deficit <= 0 or surplus_region is None:
            return
        for collector in state.collectors:
            if collector.region_type == surplus_region and collector.inventory_policy.is_pull() and collector.availability:
                collector.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=deficit,
                    source_id=self.name,
                    source_type="treatment",
                    target_region=surplus_region,
                )

    def _region_with_largest_generator_stock(self, waste_type):
        """Another region whose generators hold the most of waste_type, or None (ADR 0033)."""
        surplus_region, largest_stock = None, 0.0
        for generator in self.state.generators:
            if generator.region_type == self.region_type or waste_type not in generator.waste_streams:
                continue
            if generator.waste_streams[waste_type].volume > largest_stock:
                surplus_region, largest_stock = generator.region_type, generator.waste_streams[waste_type].volume
        return surplus_region

    def _get_prioritized_transformations(self):
        """Get transformations sorted by priority based on current system state.

        The demand component is a finished-goods shortfall term: the output type
        whose inventory is most depleted relative to its buffer scores highest,
        steering production toward what most needs restocking (ADR 0002, Phase F).
        Symmetric across PUSH and PULL; bounded to [0, 1].
        """
        transformation_scores = []

        for (input_type, output_type), transformation in self.transformations.items():
            product_key = output_type.value.lower()
            abc_priority = self.abc_priority_map.get(product_key, 0.5)

            capacity = self.finished_goods.capacity.get(output_type, 0.0)
            if capacity > 0:
                current = self.finished_goods.current_storage[output_type]
                demand_score = max(0.0, capacity - current) / capacity
            else:
                demand_score = 0.0

            efficiency_score = self._get_transformation_efficiency(transformation)
            input_availability = min(
                self.waste_storage.get(input_type, 0) / INPUT_AVAILABILITY_SATURATION_M3, 1.0
            )

            total_score = (
                (abc_priority * ABC_PRIORITY_SCORE_MULTIPLIER)
                + demand_score + efficiency_score + input_availability
            )

            transformation_scores.append(((input_type, output_type), transformation, total_score))

        transformation_scores.sort(key=lambda x: x[2], reverse=True)
        return [(key, transform) for key, transform, _ in transformation_scores]

    def _apply_status_throughput_effects(self):
        """Scale processing capacity by status-driven operational efficiency."""
        match self.status:
            case EntityStatus.FAILED | EntityStatus.RECOVERING:
                self.processing_capacity_per_tick_m3 = (
                    self.initial_processing_capacity_per_tick_m3 * self.get_operational_efficiency()
                )
            case EntityStatus.OPERATIONAL:
                self.processing_capacity_per_tick_m3 = self.initial_processing_capacity_per_tick_m3

    def _process_available_waste(self):
        """Processes waste based on prioritized transformations."""
        sorted_transformations = self._get_prioritized_transformations()
        for (input_type, output_type), transformation in sorted_transformations:
            if self.waste_storage.get(input_type, 0) > 0:
                self._process_waste_transformation(input_type, output_type, transformation)

    def _absorb_market_signals(self, current_time):
        """Add the Consumption Events behind new Market Signals to the backlog (PULL).

        ADR 0002 (Phase E): PULL production is event-triggered. The operator scans
        its own unacknowledged Market Signals, reads the Consumption Events they
        reference, and adds each producible product's ``consumed`` volume to the
        PULL Production Backlog (ADR 0020, ADR 0029). The backlog starts at
        finished-goods capacity minus initial stock, so finished goods plus
        backlog stays at capacity: a base-stock rule with lost sales, replacing
        what was sold up to the level PUSH produces up to. Runs every tick, FAILED ticks
        included: an outage stops production, not the order book, so a signal is
        never pruned unread.
        """
        market_signals = [
            signal for signal in self.kanban_manager.get_signals(current_time)
            if signal.get("source_type") == "market" and signal.get("source_id") == self.name
        ]
        if not market_signals:
            return

        signal_timestamps = {signal["timestamp"] for signal in market_signals}
        for event in self.state.consumption_events:
            if (
                event["operator"] == self.name
                and event["timestamp"] in signal_timestamps
                and event["reason"] != "no_capability"
            ):
                product = event["product"]
                self.pull_production_backlog_m3_by_product[product] = (
                    self.pull_production_backlog_m3_by_product.get(product, 0.0) + event["consumed"]
                )

        for signal in market_signals:
            self.kanban_manager.acknowledge_signal(signal["id"])

    def _produce_for_backlog(self):
        """Produce against the PULL Production Backlog (PULL).

        Each product is produced up to its backlog volume (clamped by waste,
        this tick's capacity and finished-goods headroom in
        ``_process_waste_transformation``), preserving ABC prioritization; what
        is produced is drawn down and the remainder carries to the next tick.
        This keeps the bullwhip contrast ``var(production) ~= var(attempted)``
        and the PUSH/PULL distinction crisp; PUSH retains the autonomous
        ``_process_available_waste`` loop.
        """
        for (input_type, output_type), transformation in self._get_prioritized_transformations():
            product = output_type.value.lower()
            remaining = self.pull_production_backlog_m3_by_product.get(product, 0.0)
            if remaining <= 0 or self.waste_storage.get(input_type, 0) <= 0:
                continue
            produced = self._process_waste_transformation(
                input_type, output_type, transformation, output_cap=remaining
            )
            self.pull_production_backlog_m3_by_product[product] = remaining - produced

    def run_facility(self):
        """Main process loop for the treatment facility."""
        while True:
            current_time = self.env.now
            demand_driven = self.inventory_policy_behavior.treatment_is_demand_driven()

            if demand_driven:
                self._absorb_market_signals(current_time)

            if self.apply_failure_tick():
                yield self.env.timeout(OPERATING_TICK_DAYS)
                continue

            if demand_driven:
                self._produce_for_backlog()
            else:
                self._process_available_waste()

            yield self.env.timeout(OPERATING_TICK_DAYS)

    def _process_waste_transformation(self, input_type, output_type, transformation, output_cap=None):
        """Process a single waste transformation.

        ``output_cap`` (PULL, ADR 0002 Phase E) bounds production to the
        demand-driven target: when provided, ``output_cap / efficiency`` joins the
        input-waste, processing-capacity and finished-goods-headroom clamps. PUSH
        callers omit it. Returns the output volume produced (0.0 when nothing was
        processed) so the PULL caller can draw down its per-product target.
        """

        final_products = {
            OutputType.MDF,
            OutputType.PARTICLE_BOARD,
            OutputType.OSB
        }
        if input_type in final_products:
            return 0.0

        efficiency = min(self._get_transformation_efficiency(transformation), 1.0)

        headroom = self.finished_goods.capacity.get(output_type, 0.0) - self.finished_goods.current_storage[output_type]
        if headroom <= 0:
            return 0.0

        clamps = [
            self.waste_storage[input_type],
            self.processing_capacity_per_tick_m3,
            headroom / efficiency,
        ]
        if output_cap is not None:
            clamps.append(output_cap / efficiency)
        amount_to_process = min(clamps)

        if amount_to_process <= 0:
            return 0.0

        output_amount = amount_to_process * efficiency

        self._update_waste_storage(input_type, amount_to_process, output_amount)

        if output_type in final_products:
            self.finished_goods.current_storage[output_type] += output_amount

            self.expected_output_volume_from_intake_m3 += amount_to_process * efficiency

            if output_type == OutputType.MDF:
                self.product_volumes["mdf"] += output_amount
            elif output_type == OutputType.PARTICLE_BOARD:
                self.product_volumes["particle_board"] += output_amount
            elif output_type == OutputType.OSB:
                self.product_volumes["osb"] += output_amount
        else:
            logging.warning(f"[{self.name}] Unclassified output: {output_amount:.2f} m³ of {output_type.value} from {input_type.value}")

        self._track_treatment_properties(amount_to_process, transformation)

        return output_amount

    def _get_transformation_efficiency(self, transformation):
        """Calculate transformation efficiency with uncertainty if applicable"""
        efficiency = transformation.conversion_efficiency
        if self.uncertainty_set:
            if (
                hasattr(self.uncertainty_set.treatment_conversion, "__len__")
                and len(self.uncertainty_set.treatment_conversion) == 2
            ):
                mean, std = self.uncertainty_set.treatment_conversion
                efficiency = np.clip(self.rng.normal(mean * efficiency, std), 0.6, 1.0)
        return efficiency

    def _update_waste_storage(self, input_type, amount_to_process, output_amount):
        """Update waste storage and track raw production"""
        self.waste_storage[input_type] -= amount_to_process
        self.processed_volumes[input_type] += amount_to_process

    def _track_treatment_properties(self, amount_to_process, transformation):
        """Track energy and operational costs"""
        energy_cost = (
            amount_to_process * transformation.energy_required * self.energy_consumption
        )
        operational_cost = amount_to_process * self.operational_costs
        environmental_impact_emissions = amount_to_process * self.environmental_impact

        environmental_cost = (
            environmental_impact_emissions * CARBON_PRICE_EUR_PER_KG_CO2E
        )

        monitor = self.waste_monitor
        name = self.name
        timestamp = self.env.now

        monitor.update_entity_costs(
            entity_name=name,
            entity_type="treatment",
            energy_cost=energy_cost,
            processing_cost=operational_cost + environmental_cost,
            transport_cost=0.0,
        )

        monitor.record_emission(
            entity_name=name,
            kind="carbon_emissions",
            kgco2e=environmental_impact_emissions,
            timestamp=timestamp,
        )

    def request_waste_directly(self, required_waste: float, input_waste_types: List[WasteType]) -> Dict[WasteType, float]:
        """Request waste with local/cross-region routing split"""
        from config.constants import LOCAL_COLLECTION_RATIO
        collected_waste = {}
        local_portion = required_waste * LOCAL_COLLECTION_RATIO
        cross_region_portion = required_waste * (1.0 - LOCAL_COLLECTION_RATIO)

        remaining_local = self._collect_from_local(local_portion, input_waste_types, collected_waste)

        remaining_cross_region = self._collect_from_cross_region(cross_region_portion, input_waste_types, collected_waste)

        total_remaining = remaining_local + remaining_cross_region
        if total_remaining > 0:
            self._collect_with_fallback(total_remaining, input_waste_types, collected_waste)

        return collected_waste

    def _drain_collectors(self, collectors, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Drain pre-filtered collectors via the local intake path until satisfied. A drain
        from another region is charged as one loaded trip over the distance (ADR 0037)."""
        remaining = amount_to_collect
        for collector in collectors:
            if remaining <= 0: break

            drained = collector.provide_waste_for_treatment(remaining, waste_types, treatment_name=self.name)
            if drained and collector.region_type != self.region_type:
                collector._record_trip_cost_and_emissions(drained, get_distance(collector.region_type, self.region_type))

            for waste_type, amount in drained.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

    def _collect_from_local(self, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Collect waste from local collectors."""
        local_collectors = [c for c in self.state.collectors if c.region_type == self.region_type and c.availability]
        return self._drain_collectors(local_collectors, amount_to_collect, waste_types, collected_waste)

    def _collect_from_cross_region(self, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Reposition waste from cross-region collectors via transport.

        A collector-to-collector repositioning move (ADR 0009): waste is removed
        from the remote collector and routed to a collector in this region, where
        it lands in the collection center and later reaches treatment via the local
        intake path (``provide_waste_for_treatment``). It is therefore NOT added to
        ``collected_waste`` here -- doing so would double-count it in the waste-side
        mass balance. The volume still satisfies the cross-region portion of the
        request (deducted from ``remaining``) but reaches treatment only on the
        later local pickup.
        """
        if amount_to_collect <= 0: return 0.0

        state = self.state
        remote_collectors = [c for c in state.collectors if c.region_type != self.region_type and c.availability]
        remote_collectors.sort(key=lambda c: get_distance(self.region_type, c.region_type))

        remaining = amount_to_collect
        for collector in remote_collectors[:3]:
            if remaining <= 0: break

            transport_collected = self._request_via_transport(collector, remaining, waste_types)
            for waste_type, amount in transport_collected.items():
                remaining -= amount
        return remaining

    def _collect_with_fallback(self, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Collect waste from any available collector as a fallback."""
        all_collectors = [c for c in self.state.collectors if c.availability]
        return self._drain_collectors(all_collectors, amount_to_collect, waste_types, collected_waste)

    def _request_via_transport(self, collector, amount: float, waste_types: List[WasteType]) -> Dict[WasteType, float]:
        """Request waste via transport system"""

        available_waste = self._get_available_waste_from_collector(collector, amount, waste_types)

        transported_waste = {}
        for waste_type, volume in available_waste.items():
            if volume > 0:

                success = collector.transfer_waste_to_region(
                    waste_type, volume, self.region_type
                )

                if success:
                    transported_waste[waste_type] = volume
                else:
                    print(f"[TRANSPORT FAILED] Could not schedule transport for {waste_type.value}")

        return transported_waste

    def _get_available_waste_from_collector(self, collector, max_amount: float, waste_types: List[WasteType]) -> Dict[WasteType, float]:
        """Check what waste is available from a collector"""
        available_waste = {}
        remaining_capacity = max_amount

        for waste_type in waste_types:
            if remaining_capacity <= 0:
                break

            available_in_storage = (collector.collection_center.current_storage[waste_type]
                                    - collector.transport_manager.queued_volume(collector.name, waste_type))
            if available_in_storage > 0:
                can_take = min(available_in_storage, remaining_capacity)
                available_waste[waste_type] = can_take
                remaining_capacity -= can_take

        return available_waste

    def trigger_collection(self, order_volumes: Dict[WasteType, float]):
        """Request each ordered waste type separately (ADR 0026).

        A single request across all types lets the first sorted type with stock
        fill the whole order, starving the types after it.
        """
        collected_waste = {}
        for waste_type in sorted(order_volumes, key=lambda waste_type: waste_type.value):
            if order_volumes[waste_type] <= 0:
                continue
            for collected_type, volume in self.request_waste_directly(order_volumes[waste_type], [waste_type]).items():
                collected_waste[collected_type] = collected_waste.get(collected_type, 0.0) + volume

        if not collected_waste or sum(collected_waste.values()) == 0:
            return 0, 0

        self.waste_monitor.track_processing(self, self.env.now)

        actually_stored = self._add_to_storage(collected_waste)

        return actually_stored, sum(collected_waste.values())

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Build the full catalogue fallback when no transformations are injected."""
        transformations = {}

        for input_type, (efficiency, energy) in TRANSFORMATION_CATALOGUE.items():
            for output_type in WASTE_TO_OUTPUT_TYPES[input_type]:
                key = (input_type, output_type)
                transformations[key] = WasteTransformation(
                    input_type=input_type,
                    output_type=output_type,
                    conversion_efficiency=efficiency,
                    energy_required=energy,
                )
        return transformations

    def _add_to_storage(self, waste_amounts: Dict[WasteType, float]) -> float:
        """Add waste to storage considering capacity constraints"""
        if not waste_amounts:
            return 0.0

        allowed_additions, overflow_amount = check_storage_capacity(
            self.waste_storage,
            waste_amounts,
            self.waste_storage_capacity
        )

        if overflow_amount > 0:
            compute_and_handle_overflow(self, waste_amounts, allowed_additions)

        total_added = 0.0
        for waste_type, amount in allowed_additions.items():
            self._waste_storage[waste_type] += amount
            total_added += amount

        return total_added
