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
from models.products import ProductDataManager
from utils.capacity_utils import (
    handle_storage_event,
    check_storage_capacity,
    split_overflow_by_type,
)
from config.constants import (
    INITIAL_INVENTORY_FRACTION,
    PROCESSING_CAPACITY_FRACTION,
    CARBON_PRICE_EUR_PER_KG_CO2E,
)

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
        market_share: float = 0.0,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        stock_strategy_behavior = None,
        inventory_policy_behavior = None,
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

        self.stock_strategy_behavior = stock_strategy_behavior or build_stock_strategy(stock_strategy)
        self.inventory_policy_behavior = inventory_policy_behavior or build_inventory_policy(inventory_policy)

        self.kanban_manager = kanban_manager or KanbanManager()
        self.state = state
        self.env = env
        self.name = name
        self.facility_type = "treatment"
        self.utilization_history = []
        self.utilization_window = 10
        self.processing_time = processing_time
        self.waste_storage_capacity = waste_storage_capacity
        self.energy_consumption = energy_consumption
        self.operational_costs = operational_costs
        self.environmental_impact = environmental_impact
        self.processing_capacity = self.waste_storage_capacity * PROCESSING_CAPACITY_FRACTION
        self.initial_processing_capacity = self.processing_capacity
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')]
        # Share of national market demand presented each consumption tick,
        # proportional to processing capacity; set by SimulationManager (ADR 0002).
        self.market_share = market_share
        # Waste storage primed to ~2 weeks of producible throughput (ADR 0002,
        # Phase C); collection self-corrects the mix within ~2 weeks.
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
        # Yield-bridge accumulator (G1): cumulative intake x efficiency, reconciled
        # against deposited product_volumes by MassBalanceMonitor.check_yield_bridge.
        self.expected_output_volume = 0.0

        self.product_manager = ProductDataManager()

        # Finished-goods inventory: per-product capacity sized to a fixed demand
        # buffer, primed to INITIAL_INVENTORY_FRACTION of capacity (ADR 0002, Phase
        # C). Capacity covers only producible products; others stay at zero.
        finished_goods_capacity = finished_goods_capacity or {}
        self.finished_goods = ProductStorage(
            capacity=finished_goods_capacity,
            current_storage={
                output_type: INITIAL_INVENTORY_FRACTION * finished_goods_capacity.get(output_type, 0.0)
                for output_type in OutputType
            }
        )

        self.transformations = transformations or self._default_transformations()

        # ABC prioritization is always on (ADR 0002, Phase F): biogenic-carbon
        # priority weights feed the transformation scorer unconditionally.
        self.abc_priority_map = {}
        self._initialize_abc_priorities(abc_demand_config_path)

        self.process = env.process(self.run_facility())
        env.process(self.schedule_collection_requests())

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
        """Initialize ABC priorities - reuse existing ABCAnalyzer"""
        try:
            analyzer = BiogenicCarbonABCAnalyzer(config_path)
            classifications = analyzer.perform_abc_classification()

            self.abc_priority_map = {
                item.product_type: item.priority_weight
                for item in classifications
            }

        except Exception as e:
            logging.warning(f"[{self.name}] ABC initialization failed: {e}, using default priorities")
            self.abc_priority_map = {
                "osb": 1.0,
                "particle_board": 0.7,
                "mdf": 0.4
            }

    def _should_trigger_collection_based_on_strategy(self) -> bool:
        """Determine if collection should fire, based purely on waste-storage state.

        The reorder threshold ``s`` of the (s, S) signal-volume rule (ADR 0002):
        collection triggers when total waste storage drops below the strategy's
        threshold fraction of capacity (ON_DEMAND sets ``s`` to full capacity,
        firing whenever storage is not full).
        """
        current_total = sum(self.waste_storage.values())
        return self.stock_strategy_behavior.treatment_should_reorder(
            current_total, self.waste_storage_capacity
        )

    def _get_reorder_quantity(self) -> float:
        """Order quantity for PUSH collection: top up to full capacity.

        The (s, S) order-up-to level ``S = waste_storage_capacity`` uniformly
        across strategies (ADR 0002), so the quantity is the gap to full. The
        threshold ``s`` is gated by ``_should_trigger_collection_based_on_strategy``.
        """
        current_total = sum(self.waste_storage.values())
        return max(0.0, self.waste_storage_capacity - current_total)

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

            if self._should_trigger_collection_based_on_strategy():
                signal_volume = self._get_reorder_quantity()
                if signal_volume > 0:
                    if self.inventory_policy_behavior.propagates_reorder_signals_upstream():
                        self._create_reorder_signals(signal_volume, current_time)
                    self.trigger_collection(explicit_collection_volume=signal_volume)

            yield self.env.timeout(self.processing_time)

    def _create_collection_signal(
        self, waste_type: WasteType, volume: float, timestamp: float
    ):
        """Create a collection signal for specific waste type and volume."""
        self._propagate_signal_to_collectors(waste_type, volume, timestamp)

    def _create_reorder_signals(self, total_shortage: float, timestamp: float):
        """Create reorder signals distributed across waste types."""
        input_waste_types = sorted(
            {key[0] for key in self.transformations.keys()}, key=lambda w: w.value
        )

        if not input_waste_types:
            return

        shortage_per_type = total_shortage / len(input_waste_types)

        for waste_type in input_waste_types:
            if shortage_per_type > 0:
                self._create_collection_signal(waste_type, shortage_per_type, timestamp)

    def _propagate_signal_to_collectors(self, waste_type, needed_volume, current_time):
        """Propagate signals to collectors with availability checking"""
        state = self.state

        local_collectors = [
            c for c in state.collectors 
            if (c.region_type == self.region_type and 
                c.inventory_policy == InventoryPolicy.PULL and
                c.availability and 
                c.collection_center.current_storage.get(waste_type, 0) > 0) 
        ]

        for collector in local_collectors:
            available_volume = collector.collection_center.current_storage.get(waste_type, 0)
            signal_volume = min(needed_volume, available_volume)

            if signal_volume > 0:
                collector.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=signal_volume,
                    source_id=self.name,
                    source_type="treatment"
                )

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

            # Finished-goods shortfall in [0, 1]: full buffer scores 0, empty
            # buffer scores 1. A zero-capacity output contributes no shortfall
            # rather than dividing by zero.
            capacity = self.finished_goods.capacity.get(output_type, 0.0)
            if capacity > 0:
                current = self.finished_goods.current_storage[output_type]
                demand_score = max(0.0, capacity - current) / capacity
            else:
                demand_score = 0.0

            efficiency_score = self._get_transformation_efficiency(transformation)
            input_availability = min(self.waste_storage.get(input_type, 0) / 100, 1.0)

            total_score = (abc_priority * 2.0) + demand_score + efficiency_score + input_availability

            transformation_scores.append(((input_type, output_type), transformation, total_score))

        transformation_scores.sort(key=lambda x: x[2], reverse=True)
        return [(key, transform) for key, transform, _ in transformation_scores]

    def _handle_failures(self, current_time: float):
        """Checks for and handles facility failures, updating processing capacity."""
        if not self.failure_config:
            return

        # Use the base class failure checking with proper config
        self.check_failure(current_time, self.failure_config.probability)

        match self.status:
            case EntityStatus.FAILED:
                recovery_efficiency = self.get_operational_efficiency()
                self.processing_capacity = (
                    self.initial_processing_capacity * recovery_efficiency
                )
            case EntityStatus.RECOVERING:
                recovery_efficiency = self.get_operational_efficiency()
                self.processing_capacity = self.initial_processing_capacity * recovery_efficiency
            case EntityStatus.OPERATIONAL:
                self.processing_capacity = self.initial_processing_capacity

    def _process_available_waste(self):
        """Processes waste based on prioritized transformations."""
        sorted_transformations = self._get_prioritized_transformations()
        for (input_type, output_type), transformation in sorted_transformations:
            if self.waste_storage.get(input_type, 0) > 0:
                self._process_waste_transformation(input_type, output_type, transformation)

    def _produce_for_consumption_events(self, current_time):
        """Produce in response to downstream market consumption events (PULL).

        ADR 0002 (Phase E): PULL production is event-triggered, not supply-driven.
        The operator scans its own unacknowledged Market Signals, reads the
        Consumption Events they reference, and produces each product up to the
        attempted demand volume (clamped by waste, capacity and finished-goods
        headroom in ``_process_waste_transformation``). This keeps the bullwhip
        contrast ``var(production) ~= var(attempted)`` and the PUSH/PULL
        distinction crisp; PUSH retains the autonomous ``_process_available_waste``
        loop.
        """
        market_signals = [
            signal for signal in self.kanban_manager.get_signals(current_time)
            if signal.get("source_type") == "market" and signal.get("source_id") == self.name
        ]
        if not market_signals:
            return

        # Per-product demand target = summed ``attempted`` across the Consumption
        # Events these signals reference, matched by (operator, signal timestamp).
        # Ticks land on exact multiples of CONSUMPTION_INTERVAL_DAYS and each
        # signal shares its events' timestamp, so float equality is safe.
        signal_timestamps = {signal["timestamp"] for signal in market_signals}
        state = self.state
        targets: Dict[str, float] = {}
        for event in state.consumption_events:
            if event["operator"] == self.name and event["timestamp"] in signal_timestamps:
                targets[event["product"]] = targets.get(event["product"], 0.0) + event["attempted"]

        # Produce against targets, preserving ABC prioritization. Each
        # transformation draws down the remaining target for its output product.
        for (input_type, output_type), transformation in self._get_prioritized_transformations():
            product = output_type.value.lower()
            remaining = targets.get(product, 0.0)
            if remaining <= 0 or self.waste_storage.get(input_type, 0) <= 0:
                continue
            produced = self._process_waste_transformation(
                input_type, output_type, transformation, output_cap=remaining
            )
            targets[product] = remaining - produced

        for signal in market_signals:
            self.kanban_manager.acknowledge_signal(signal["id"])

    def run_facility(self):
        """Main process loop for the treatment facility."""
        while True:
            current_time = self.env.now
            self._handle_failures(current_time)

            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.processing_time)
                continue

            # PUSH produces autonomously from available waste (supply-driven);
            # PULL produces only in response to downstream consumption events
            # (demand-driven). ADR 0002, Phase E.
            if self.inventory_policy_behavior.treatment_is_demand_driven():
                self._produce_for_consumption_events(current_time)
            else:
                self._process_available_waste()

            yield self.env.timeout(self.processing_time)

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

        # Per-output finished-goods headroom clamp (ADR 0002, Phase C). Production
        # is throttled per output type so a saturated buffer for one product never
        # stalls or overflows another. With no overflow there is no silent product
        # discard and no secondary storage buffer.
        headroom = self.finished_goods.capacity.get(output_type, 0.0) - self.finished_goods.current_storage[output_type]
        if headroom <= 0:
            return 0.0

        clamps = [
            self.waste_storage[input_type],
            self.processing_capacity,
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

            # Yield-bridge expectation (G1): derived from intake, independent of
            # the output_amount path above, so the two diverge if a yield is wrong.
            self.expected_output_volume += amount_to_process * efficiency

            if output_type == OutputType.MDF:
                self.product_volumes["mdf"] += output_amount # m³
            elif output_type == OutputType.PARTICLE_BOARD:
                self.product_volumes["particle_board"] += output_amount # m³
            elif output_type == OutputType.OSB:
                self.product_volumes["osb"] += output_amount # m³
        else:
            logging.warning(f"[{self.name}] Unclassified output: {output_amount:.2f} m³ of {output_type.value} from {input_type.value}")

        self._track_treatment_properties(amount_to_process, transformation)
        self._update_utilization_metrics(amount_to_process)

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

        monitor.track_environmental_impact(
            entity_name=name,
            environmental_impact=environmental_impact_emissions,  # kg CO₂e
            timestamp=timestamp,
            impact_category="carbon_emissions",
        )

    def _update_utilization_metrics(self, amount_to_process):
        """Update utilization history for capacity management"""
        if self.processing_capacity <= 0:
            current_utilization = 0.0
        else:
            current_utilization = amount_to_process / self.processing_capacity
        self.utilization_history.append(current_utilization)
        if len(self.utilization_history) > self.utilization_window:
            self.utilization_history.pop(0)

    def request_waste_directly(self, required_waste: float, input_waste_types: List[WasteType]) -> Dict[WasteType, float]:
        """Request waste with local/cross-region routing split"""
        from config.constants import LOCAL_COLLECTION_RATIO
        collected_waste = {}
        local_portion = required_waste * LOCAL_COLLECTION_RATIO
        cross_region_portion = required_waste * (1.0 - LOCAL_COLLECTION_RATIO)

        # 1. Local collection
        remaining_local = self._collect_from_local(local_portion, input_waste_types, collected_waste)

        # 2. Cross-region collection
        remaining_cross_region = self._collect_from_cross_region(cross_region_portion, input_waste_types, collected_waste)

        # 3. Fallback collection
        total_remaining = remaining_local + remaining_cross_region
        if total_remaining > 0:
            self._collect_with_fallback(total_remaining, input_waste_types, collected_waste)

        return collected_waste

    def _collect_from_local(self, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Collect waste from local collectors."""
        state = self.state
        local_collectors = [c for c in state.collectors if c.region_type == self.region_type and c.availability]

        remaining = amount_to_collect
        for collector in local_collectors:
            if remaining <= 0: break

            local_collected = collector.provide_waste_for_treatment(remaining, waste_types, treatment_name=self.name)

            for waste_type, amount in local_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

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
        state = self.state
        all_collectors = [c for c in state.collectors if c.availability]

        remaining = amount_to_collect
        for collector in all_collectors:
            if remaining <= 0: break
            fallback_collected = collector.provide_waste_for_treatment(remaining, waste_types, treatment_name=self.name)
            for waste_type, amount in fallback_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

    def _request_via_transport(self, collector, amount: float, waste_types: List[WasteType]) -> Dict[WasteType, float]:
        """Request waste via transport system"""

        available_waste = self._get_available_waste_from_collector(collector, amount, waste_types)

        transported_waste = {}
        for waste_type, volume in available_waste.items():
            if volume > 0:

                # Call transport system
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

            available_in_storage = collector.collection_center.current_storage[waste_type]
            if available_in_storage > 0:
                can_take = min(available_in_storage, remaining_capacity)
                available_waste[waste_type] = can_take
                remaining_capacity -= can_take

        return available_waste

    def trigger_collection(self, explicit_collection_volume: float):
        """Request waste collection of an explicit order volume.

        The order volume is the (s, S) signal volume computed by the caller and
        used directly (no ceiling-derived fallback; ADR 0002).
        """
        required_waste = explicit_collection_volume

        if required_waste <= 0:
            return 0, 0

        input_waste_types = sorted(
            {key[0] for key in self.transformations.keys()}, key=lambda w: w.value
        )

        collected_waste = self.request_waste_directly(required_waste, input_waste_types)

        if not collected_waste or sum(collected_waste.values()) == 0:
            return 0, 0

        self.waste_monitor.track_processing(self, self.env.now)

        actually_stored = self._add_to_storage(collected_waste)

        return actually_stored, sum(collected_waste.values())

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        base_transformations = {
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95),
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),
            WasteType.BARK_CORK_WASTE_03_01_01: (0.85, 0.70),
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),
            WasteType.FORESTRY_WASTE_02_01_07: (0.82, 0.75),
            WasteType.OTHER_WOOD_WASTE_03_01_99: (0.85, 0.65),
        }

        transformations = {}

        default_output_mapping = {
            WasteType.CONSTRUCTION_WOOD_17_02_01: [
                OutputType.PARTICLE_BOARD,    
                OutputType.OSB,    
            ],
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: [
                OutputType.PARTICLE_BOARD,  
                OutputType.MDF,    
                OutputType.OSB,   
            ],
            WasteType.WOODEN_PACKAGING_15_01_03: [
                OutputType.PARTICLE_BOARD,  
                OutputType.OSB,    
            ],
            WasteType.BARK_CORK_WASTE_03_01_01: [
                OutputType.MDF,    
                OutputType.PARTICLE_BOARD,  
            ],
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: [
                OutputType.PARTICLE_BOARD, 
                OutputType.MDF,   
                OutputType.OSB,    
            ],
            WasteType.PAPER_PACKAGING_15_01_01: [
                OutputType.MDF,
            ],
            WasteType.FORESTRY_WASTE_02_01_07: [
                OutputType.PARTICLE_BOARD,
                OutputType.MDF,
            ],
            WasteType.OTHER_WOOD_WASTE_03_01_99: [
                OutputType.PARTICLE_BOARD,
                OutputType.MDF,
                OutputType.OSB,
            ],
        }

        for input_type, (efficiency, energy) in base_transformations.items():
            for output_type in default_output_mapping[input_type]:
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
            # check_storage_capacity already scaled each type proportionally, so the
            # per-type overflow is exactly what was skimmed off each addition. Sorted
            # by WasteType.value for deterministic iteration (CRN guard).
            per_type_overflow = {
                waste_type: waste_amounts[waste_type]
                - allowed_additions.get(waste_type, 0.0)
                for waste_type in sorted(
                    waste_amounts, key=lambda waste_type: waste_type.value
                )
            }
            handle_storage_event(self, per_type_overflow)

        total_added = 0.0
        for waste_type, amount in allowed_additions.items():
            self._waste_storage[waste_type] += amount
            total_added += amount

        return total_added
