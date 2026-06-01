import numpy as np
from typing import Dict, Optional
from core.abc_analysis import BiogenicCarbonABCAnalyzer
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from models.data_classes import WasteTransformation, OperationalEntity, ProductStorage
from models.distances import get_distance
from models.enums import OutputType, RegionType, StockStrategy, WasteType, EntityStatus
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from core.kanban_manager import KanbanManager
from models.enums import InventoryPolicy
from models.products import ProductDataManager
from utils.capacity_utils import handle_storage_event, check_storage_capacity
from config.constants import INITIAL_INVENTORY_FRACTION

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
        conversion_rate,
        operational_costs,
        region: str,
        uncertainty_set=None,
        transformations: Optional[Dict[WasteType, WasteTransformation]] = None,
        waste_monitor: Optional[WasteMonitor] = None,
        kanban_manager: KanbanManager = None,
        finished_goods_capacity: Optional[Dict[OutputType, float]] = None,
        initial_waste_storage: Optional[Dict[WasteType, float]] = None,
        market_share: float = 0.0,
        scenario_config=None,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        transport_manager: Optional[PointToPointTransport] = None,
        enable_abc_prioritization: bool = True,
        abc_demand_config_path: str = "data/demand.json",
        failure_config = None,
        seed = None
    ):
        self.uncertainty_set = uncertainty_set

        if failure_config is None and uncertainty_set:
            failure_config = uncertainty_set.treatment_failure

        super().__init__(failure_config=failure_config, seed=seed)

        self.waste_monitor = waste_monitor
        self.scenario_config = scenario_config
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy

        if waste_monitor is None:
            raise ValueError("waste_monitor is required for TreatmentOperator")
        if self.inventory_policy is None:
            raise ValueError("inventory_policy must be provided")
        if self.stock_strategy is None:
            raise ValueError("stock_strategy must be provided")

        self.kanban_manager = kanban_manager or KanbanManager()
        self.transport_manager = transport_manager or PointToPointTransport()
        self.env = env
        self.name = name
        self.facility_type = "treatment"
        self.utilization_history = []
        self.utilization_window = 10
        self.processing_time = processing_time
        self.waste_storage_capacity = waste_storage_capacity
        self.energy_consumption = energy_consumption
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs
        self.environmental_impact = environmental_impact
        self.processing_capacity = self.waste_storage_capacity * 0.8
        self.initial_processing_capacity = self.processing_capacity
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')]
        # Share of national market demand this operator is presented each
        # consumption tick, proportional to its processing capacity. Assigned
        # at construction by SimulationManager (demand-as-consumption, ADR 0002).
        self.market_share = market_share
        self.demand = 0
        self.demand_history = []
        self.minimum_required_waste = 0.1
        self.production_history = []
        # Waste storage primed to ~2 weeks of producible throughput (ADR 0002,
        # Phase C); collection self-corrects the mix within ~2 weeks.
        self._waste_storage = dict.fromkeys(WasteType, 0.0)
        if initial_waste_storage:
            for waste_type, volume in initial_waste_storage.items():
                self._waste_storage[waste_type] = volume
        self.total_products_created = 0.0
        self.processed_volumes = dict.fromkeys(WasteType, 0.0)
        self.product_volumes = {
            "mdf": 0.0,
            "particle_board": 0.0,
            "osb": 0.0
        }

        # Initialize product data manager for accessing product specifications
        self.product_manager = ProductDataManager()

        # Finished-goods inventory: per-product capacity sized to a fixed buffer
        # of expected demand, primed to INITIAL_INVENTORY_FRACTION of capacity so
        # the run starts warmed up rather than empty (ADR 0002, Phase C). Capacity
        # covers only producible products; others stay at zero.
        finished_goods_capacity = finished_goods_capacity or {}
        self.finished_goods = ProductStorage(
            capacity=finished_goods_capacity,
            current_storage={
                output_type: INITIAL_INVENTORY_FRACTION * finished_goods_capacity.get(output_type, 0.0)
                for output_type in OutputType
            }
        )

        # Stochastic components
        self.uncertainty_set = uncertainty_set
        self.transformation_efficiency = 0.95
        # Transformations
        self.transformations = transformations or self._default_transformations()

        self.enable_abc_prioritization = enable_abc_prioritization
        self.abc_priority_map = {}

        if self.enable_abc_prioritization:
            self._initialize_abc_priorities(abc_demand_config_path)

        from config.constants import ON_DEMAND_BUFFER_RATIO, ON_DEMAND_TARGET_RATIO
        self.on_demand_buffer_ratio = ON_DEMAND_BUFFER_RATIO
        self.on_demand_target_ratio = ON_DEMAND_TARGET_RATIO

        # Start processes
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
                overflow_amount, 
                self.region
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
            import logging
            logging.warning(f"[{self.name}] ABC initialization failed: {e}, using default priorities")
            self.abc_priority_map = {
                "osb": 1.0,
                "particle_board": 0.7,
                "mdf": 0.4
            }

    def _apply_stock_strategy_to_demand_calculation(self, base_demand: float) -> float:
        """Apply stock strategy considerations to demand calculation"""
        current_total = sum(self.waste_storage.values())
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()

        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                if any(demand > 0 for demand in unmet_demands.values()):
                    total_active_demand = sum(unmet_demands.values())
                    return min(base_demand, total_active_demand * 1.1)
                else:
                    print(
                        f"[{self.name}] No active demand, using base demand: {base_demand}"
                    )
                    reorder_point = (
                        self.waste_storage_capacity * self.on_demand_buffer_ratio
                    )
                    target_level = (
                        self.waste_storage_capacity * self.on_demand_target_ratio
                    )
                    if current_total < reorder_point:
                        shortage = max(0.0, target_level - current_total)
                        return min(base_demand, shortage)
                    return 0.0

            case StockStrategy.REORDER_50:
                reorder_point = self.waste_storage_capacity * 0.5
                if current_total < reorder_point:
                    shortage = reorder_point - current_total
                    return max(base_demand, shortage)
                else:
                    return 0.0

            case StockStrategy.REORDER_90:
                reorder_point = self.waste_storage_capacity * 0.9
                if current_total < reorder_point:
                    shortage = reorder_point - current_total
                    return max(base_demand, shortage)
                else:
                    return 0.0

        return base_demand

    def _should_trigger_collection_based_on_strategy(self) -> bool:
        """Determine if collection should be triggered based on stock strategy"""
        current_total = sum(self.waste_storage.values())
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()

        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                has_active_demand = any(demand > 0 for demand in unmet_demands.values())
                below_buffer = current_total < (
                    self.waste_storage_capacity * self.on_demand_buffer_ratio
                )
                can_process_existing = current_total > self.minimum_required_waste
                has_processing_capacity = (
                    self.current_storage < self.waste_storage_capacity
                )
                return (
                    has_active_demand
                    or below_buffer
                    or (can_process_existing and has_processing_capacity)
                )

            case StockStrategy.REORDER_50:
                reorder_point = self.waste_storage_capacity * 0.5
                return current_total < reorder_point

            case StockStrategy.REORDER_90:
                reorder_point = self.waste_storage_capacity * 0.9
                return current_total < reorder_point

        return True  

    def _get_reorder_quantity(self) -> float:
        """Calculate how much to reorder based on strategy"""
        current_total = sum(self.waste_storage.values())

        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                state = SimulationState.get_instance()
                unmet_demands = state.get_unmet_demands()
                total_current_demand = sum(unmet_demands.values())
                if total_current_demand > 0:
                    return total_current_demand
                target_level = self.waste_storage_capacity * self.on_demand_target_ratio
                return max(0.0, target_level - current_total)

            case StockStrategy.REORDER_50:
                reorder_point = self.waste_storage_capacity * 0.5
                return max(0.0, reorder_point - current_total)

            case StockStrategy.REORDER_90:
                reorder_point = self.waste_storage_capacity * 0.9
                return max(0.0, reorder_point - current_total)

        return self.processing_capacity

    def schedule_collection_requests(self):
        """Transport-safe PUSH vs PULL with startup protection"""
        while True:
            current_time = self.env.now

            match self.inventory_policy:
                case InventoryPolicy.PUSH:
                    yield from self._push_collection_logic()
                case InventoryPolicy.PULL:
                    yield from self._pull_collection_logic(current_time)
                case _:
                    yield self.env.timeout(7)

    def _push_collection_logic(self):
        """PUSH: Strategy-based with proper reorder point logic"""

        # Check if we should collect based on strategy
        if not self._should_trigger_collection_based_on_strategy():
            yield self.env.timeout(self.processing_time)
            return

        # Calculate reorder quantity based on strategy
        reorder_quantity = self._get_reorder_quantity()

        if reorder_quantity > 0:
            self.demand = reorder_quantity
            self.trigger_collection()

        yield self.env.timeout(self.processing_time)

    def _pull_collection_logic(self, current_time):
        """PULL: Kanban-driven with continuous demand signaling"""
        active_signals = self.kanban_manager.get_signals(current_time)

        # Market consumption signals (source_type="market") are the downstream
        # demand trigger for the PULL refactor (ADR 0002, Phase E); the waste-
        # collection path here must not treat them as upstream waste demand.
        active_signals = [s for s in active_signals if s.get("source_type") != "market"]

        if active_signals:
            # Process existing signals
            sorted_signals = sorted(active_signals, 
                                key=lambda s: (s['priority'], current_time - s['timestamp']), 
                                reverse=True)

            total_demand = sum(signal['volume'] for signal in sorted_signals)
            self.demand = total_demand
            self.trigger_collection()

            for signal in sorted_signals:
                self.kanban_manager.acknowledge_signal(signal['id'])

        # NEW: Always check if we need more waste and generate signals accordingly
        self._continuous_demand_signaling(current_time)

        yield self.env.timeout(self.processing_time)

    def _continuous_demand_signaling(self, current_time):
        """Continuously signal for waste when needed"""

        # Check if we're running low on any input waste types
        input_waste_types = {key[0] for key in self.transformations.keys()}

        for waste_type in input_waste_types:
            current_stock = self.waste_storage.get(waste_type, 0)

            # Signal if stock is low (less than 10% of capacity per waste type)
            per_type_capacity = self.waste_storage_capacity / len(input_waste_types)
            reorder_point = per_type_capacity * 0.1

            if current_stock < reorder_point:
                needed_volume = per_type_capacity * 0.5  # Order up to 50% capacity
                self._create_collection_signal(waste_type, needed_volume, current_time, priority=7)

    def _filter_signals_by_strategy(self, signals: list) -> list:
        """Filter incoming signals based on stock strategy"""
        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                return signals

            case StockStrategy.REORDER_50:
                current_total = sum(self.waste_storage.values())
                reorder_point = self.waste_storage_capacity * 0.5
                if current_total < reorder_point:
                    return signals
                else:
                    return []

            case StockStrategy.REORDER_90:
                current_total = sum(self.waste_storage.values())
                reorder_point = self.waste_storage_capacity * 0.9
                if current_total < reorder_point:
                    return signals
                else:
                    return []  

        return signals

    def _generate_strategy_based_signals(self, current_time: float):
        """Generate signals based on stock strategy requirements"""
        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                state = SimulationState.get_instance()
                unmet_demands = state.get_unmet_demands()

                if any(demand > 0 for demand in unmet_demands.values()):
                    for waste_type, stream_volume in self.waste_storage.items():
                        if stream_volume < self.minimum_required_waste:
                            needed = self._calculate_waste_needed_for_demand(waste_type)
                            if needed > 0:
                                self._create_collection_signal(
                                    waste_type, needed, current_time, priority=9
                                )

            case StockStrategy.REORDER_50:
                reorder_point = self.waste_storage_capacity * 0.5
                current_total = sum(self.waste_storage.values())

                if current_total < reorder_point:
                    shortage = reorder_point - current_total
                    self._create_reorder_signals(shortage, current_time, priority=5)

            case StockStrategy.REORDER_90:
                reorder_point = self.waste_storage_capacity * 0.9
                current_total = sum(self.waste_storage.values())

                if current_total < reorder_point:
                    shortage = reorder_point - current_total
                    self._create_reorder_signals(shortage, current_time, priority=3)

    def _calculate_waste_needed_for_demand(self, waste_type: WasteType) -> float:
        """Calculate how much of a specific waste type is needed to fulfill current demand"""
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()

        # Find transformations that use this waste type
        relevant_transformations = [
            (key, transform) for key, transform in self.transformations.items()
            if key[0] == waste_type
        ]

        if not relevant_transformations:
            return 0.0

        total_needed = 0.0
        for (input_type, output_type), transformation in relevant_transformations:
            output_key = output_type.value.lower().replace('_', '_')
            if output_key in unmet_demands and unmet_demands[output_key] > 0:
                # Calculate waste needed to produce this demand
                efficiency = transformation.conversion_efficiency
                waste_needed = unmet_demands[output_key] / efficiency
                total_needed += waste_needed

        return total_needed

    def _create_collection_signal(
        self, waste_type: WasteType, volume: float, timestamp: float, priority: int
    ):
        """Create a collection signal for specific waste type and volume.

        NOTE: `priority` is accepted but not yet propagated downstream --
        `_propagate_signal_to_collectors` currently hardcodes the kanban
        signal priority. Wiring strategy priority through the kanban bus is
        tracked in .scratch/kanban-priority-wiring/. Do not delete the
        parameter; it documents the intended (not-yet-implemented) contract.
        """
        self._propagate_signal_to_collectors(waste_type, volume, timestamp)

    def _create_reorder_signals(self, total_shortage: float, timestamp: float, priority: int):
        """Create reorder signals distributed across waste types.

        NOTE: `priority` is accepted but not yet propagated -- see
        .scratch/kanban-priority-wiring/. Do not delete the parameter.
        """
        input_waste_types = {key[0] for key in self.transformations.keys()}

        if not input_waste_types:
            return

        shortage_per_type = total_shortage / len(input_waste_types)

        for waste_type in input_waste_types:
            if shortage_per_type > 0:
                self._create_collection_signal(waste_type, shortage_per_type, timestamp, priority)

    def _propagate_signal_to_collectors(self, waste_type, needed_volume, current_time):
        """Propagate signals to collectors with availability checking"""
        state = SimulationState.get_instance()

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
                    priority=8,  
                    timestamp=current_time,
                    volume=signal_volume,
                    source_id=self.name,
                    source_type="treatment"
                )

    def calculate_realistic_demand(self) -> float:
        """Calculate realistic demand based on stock strategy"""
        # Base calculation remains the same
        current_total = sum(self.waste_storage.values())

        available_capacity = (self.waste_storage_capacity - current_total) * 0.8
        max_processable = self.processing_capacity * 3.0

        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()
        total_unmet = sum(unmet_demands.values())

        if not self._should_trigger_collection_based_on_strategy():
            return 0.0  # Strategy says don't collect

        # Calculate base demand
        base_demand = min(
            available_capacity,
            max_processable,
            total_unmet * 0.3
        )
        strategy_demand = self._apply_stock_strategy_to_demand_calculation(base_demand)

        return max(strategy_demand, 0.0)

    def _get_prioritized_transformations(self):
        """Get transformations sorted by priority based on current demands and system state"""
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()

        if not self.enable_abc_prioritization:
            return self._get_default_prioritized_transformations(unmet_demands)

        transformation_scores = []

        for (input_type, output_type), transformation in self.transformations.items():
            product_key = output_type.value.lower().replace('_', '_')
            abc_priority = self.abc_priority_map.get(product_key, 0.5)

            current_demand = unmet_demands.get(product_key, 0)
            has_demand = current_demand > 0

            # Scoring: ABC priority + demand urgency + efficiency + input
            demand_score = min(current_demand / 5000, 1.0) if has_demand else 0.1
            efficiency_score = self._get_transformation_efficiency(transformation)
            input_availability = min(self.waste_storage.get(input_type, 0) / 100, 1.0)

            total_score = (abc_priority * 2.0) + demand_score + efficiency_score + input_availability

            transformation_scores.append(((input_type, output_type), transformation, total_score))

        transformation_scores.sort(key=lambda x: x[2], reverse=True)
        return [(key, transform) for key, transform, _ in transformation_scores]

    def _get_default_prioritized_transformations(self, unmet_demands):
        """Original logic (keep unchanged for fallback)"""
        if any(demand > 0 for demand in unmet_demands.values()):
            product_demands = {
                OutputType.MDF: unmet_demands.get('mdf', 0),
                OutputType.PARTICLE_BOARD: unmet_demands.get('particle_board', 0),
                OutputType.OSB: unmet_demands.get('osb', 0)
            }

            return sorted(
                self.transformations.items(),
                key=lambda x, demands=product_demands: (
                    demands.get(x[0][1], 0) > 0,
                    demands.get(x[0][1], 0),
                    self._get_transformation_efficiency(x[1]),
                ),
                reverse=True,
            )
        else:
            return sorted(
                self.transformations.items(),
                key=lambda x: self._get_transformation_efficiency(x[1]),
                reverse=True,
            )

    def request_waste_delivery(self, waste_type: WasteType, volume: float, 
                             from_region: RegionType, priority: TransportPriority = TransportPriority.NORMAL):
        """Request waste delivery from a specific region"""
        request = TransportRequest(
            origin=from_region,
            destination=self.region_type,
            waste_type=waste_type,
            volume=volume,
            priority=priority,
            request_time=self.env.now,
            requester_id=self.name
        )
        return self.transport_manager.request_transport(request)

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

    def run_facility(self):
        """Main process loop for the treatment facility."""
        while True:
            current_time = self.env.now
            self._handle_failures(current_time)

            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.processing_time)
                continue

            if self.inventory_policy == InventoryPolicy.PULL:
                self._continuous_demand_signaling(current_time)

            self._process_available_waste()
            yield self.env.timeout(self.processing_time)

    def _process_waste_transformation(self, input_type, output_type, transformation):
        """Process a single waste transformation"""

        final_products = {
            OutputType.MDF,
            OutputType.PARTICLE_BOARD,
            OutputType.OSB
        }
        if input_type in final_products:
            return

        efficiency = min(self._get_transformation_efficiency(transformation), 1.0)

        # Per-output finished-goods headroom clamp (ADR 0002, Phase C). Production
        # is throttled per output type so a saturated buffer for one product never
        # stalls or overflows another. With no overflow there is no silent product
        # discard and no secondary storage buffer.
        headroom = self.finished_goods.capacity.get(output_type, 0.0) - self.finished_goods.current_storage[output_type]
        if headroom <= 0:
            return

        amount_to_process = min(
            self.waste_storage[input_type],
            self.processing_capacity,
            headroom / efficiency,
        )

        if amount_to_process <= 0:
            return

        amount_to_process, output_amount = self._calculate_output_amounts(
            amount_to_process, efficiency
        )

        self._update_waste_storage(input_type, amount_to_process, output_amount)

        if output_type in final_products:
            self.finished_goods.current_storage[output_type] += output_amount
            self._fulfill_demand(output_type, output_amount)

            if output_type == OutputType.MDF:
                self.product_volumes["mdf"] += output_amount # m³
            elif output_type == OutputType.PARTICLE_BOARD:
                self.product_volumes["particle_board"] += output_amount # m³
            elif output_type == OutputType.OSB:
                self.product_volumes["osb"] += output_amount # m³
        else:
            print(f"[{self.name}] Unclassified output: {output_amount:.2f} m³ of {output_type.value} from {input_type.value}")

        self._track_treatment_properties(amount_to_process, transformation)
        self._update_utilization_metrics(amount_to_process)

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

    def _calculate_output_amounts(self, amount_to_process, efficiency):
        """Calculate actual processing and output amounts considering capacity constraints"""
        potential_output = amount_to_process * efficiency
        output_amount = potential_output
        return amount_to_process, output_amount

    def _update_waste_storage(self, input_type, amount_to_process, output_amount):
        """Update waste storage and track raw production"""
        self.waste_storage[input_type] -= amount_to_process
        self.processed_volumes[input_type] += amount_to_process
        self.total_products_created += output_amount

    def _fulfill_demand(self, output_type, output_amount):
        """Record cumulative production against the legacy demand ceiling.

        ADR 0002 makes the market consumption process the sole drain of
        ``finished_goods``: it removes finished goods weekly at a
        seasonally-modulated rate. This method no longer drains inventory at
        production time -- doing so front-ran the market and left only
        over-target overshoot on the shelf, contaminating per-product service
        level. It is retained only to keep ``total_products`` advancing, since
        the still-live PUSH/PULL collection triggers read it via
        ``get_unmet_demands()``. Both the bookkeeping and this method retire in
        Phase F once those triggers move off the ceiling.
        """
        state = SimulationState.get_instance()
        product_type = output_type.value.lower()

        unmet_demand = (
            state.target_demands[product_type] - state.total_products[product_type]
        )

        fulfilled_amount = min(output_amount, unmet_demand)

        if fulfilled_amount > 0:
            self.production_history.append(
                (self.env.now, output_type.value.lower(), fulfilled_amount)
            )

            state.track_product_production(product_type, fulfilled_amount, self.env.now)

    def _track_treatment_properties(self, amount_to_process, transformation):
        """Track energy and operational costs"""
        energy_cost = (
            amount_to_process * transformation.energy_required * self.energy_consumption
        )
        operational_cost = amount_to_process * self.operational_costs
        environmental_impact_emissions = amount_to_process * self.environmental_impact

        environmental_cost = (
            environmental_impact_emissions * 0.05
        )  # €0.05 per kg CO₂e (example)

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
            entity_type="treatment",
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

    def request_waste_directly(self, required_waste: float, input_waste_types: set) -> Dict[WasteType, float]:
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

    def _collect_from_local(self, amount_to_collect: float, waste_types: set, collected_waste: dict) -> float:
        """Collect waste from local collectors."""
        state = SimulationState.get_instance()
        local_collectors = [c for c in state.collectors if c.region_type == self.region_type and c.availability]

        remaining = amount_to_collect
        for collector in local_collectors:
            if remaining <= 0: break

            local_collected = collector.provide_waste_for_treatment(remaining, waste_types)

            for waste_type, amount in local_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

    def _collect_from_cross_region(self, amount_to_collect: float, waste_types: set, collected_waste: dict) -> float:
        """Collect waste from cross-region collectors via transport."""
        if amount_to_collect <= 0: return 0.0

        state = SimulationState.get_instance()
        remote_collectors = [c for c in state.collectors if c.region_type != self.region_type and c.availability]
        remote_collectors.sort(key=lambda c: get_distance(self.region_type, c.region_type))

        remaining = amount_to_collect
        for collector in remote_collectors[:3]:
            if remaining <= 0: break

            transport_collected = self._request_via_transport(collector, remaining, waste_types)
            for waste_type, amount in transport_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

    def _collect_with_fallback(self, amount_to_collect: float, waste_types: set, collected_waste: dict) -> float:
        """Collect waste from any available collector as a fallback."""
        state = SimulationState.get_instance()
        all_collectors = [c for c in state.collectors if c.availability]

        remaining = amount_to_collect
        for collector in all_collectors:
            if remaining <= 0: break
            fallback_collected = collector.provide_waste_for_treatment(remaining, waste_types)
            for waste_type, amount in fallback_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining -= amount
        return remaining

    def _request_via_transport(self, collector, amount: float, waste_types: set) -> Dict[WasteType, float]:
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

    def _get_available_waste_from_collector(self, collector, max_amount: float, waste_types: set) -> Dict[WasteType, float]:
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

    def trigger_collection(self):
        """Request waste collection based on current needs"""
        required_waste = self.calculate_realistic_demand()
        if required_waste <= 0:
            return 0, 0

        input_waste_types = {key[0] for key in self.transformations.keys()}

        collected_waste = self.request_waste_directly(required_waste, input_waste_types)

        if not collected_waste or sum(collected_waste.values()) == 0:
            return 0, 0

        self.demand_history.append((self.env.now, required_waste))
        self.waste_monitor.track_processing(self, self.env.now)

        actually_stored = self._add_to_storage(collected_waste)
        if actually_stored < sum(collected_waste.values()):
            overflow_amount = sum(collected_waste.values()) - actually_stored
            handle_storage_event(
                self, 
                overflow_amount, 
                self.region
            )

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
            handle_storage_event(
                self, 
                overflow_amount, 
                self.region
            )

        total_added = 0.0
        for waste_type, amount in allowed_additions.items():
            self._waste_storage[waste_type] += amount
            total_added += amount

        return total_added

    def get_product_properties(self, product_type: str) -> dict:
        """Get product properties including wood density and biogenic carbon stock"""
        product_spec = self.product_manager.get_product_specification(product_type)
        if not product_spec:
            return {}

        return {
            "wood_density_min": product_spec.wood_density_min,
            "wood_density_max": product_spec.wood_density_max,
            "wood_density_avg": product_spec.wood_density_avg,
            "biogenic_carbon_stock": product_spec.biogenic_carbon_stock,
            "biogenic_stock_per_kg_wood": product_spec.biogenic_stock_per_kg_wood
        }

    def calculate_total_biogenic_carbon_stored(self) -> dict:
        """Calculate total biogenic carbon stored in all produced products"""
        total_biogenic_storage = {}

        for product_type, volume in self.product_volumes.items():
            if volume > 0:
                product_spec = self.product_manager.get_product_specification(product_type)
                if product_spec:
                    total_biogenic_storage[product_type] = {
                        "volume_m3": volume,
                        "biogenic_carbon_total": volume * product_spec.biogenic_carbon_stock,
                        "wood_content_kg": volume * product_spec.wood_density_avg
                    }

        return total_biogenic_storage

    def get_wood_density_for_product(self, product_type: str) -> float:
        """Get average wood density for a specific product type"""
        product_spec = self.product_manager.get_product_specification(product_type)
        return product_spec.wood_density_avg if product_spec else 0.0

    def get_biogenic_carbon_stock_for_product(self, product_type: str) -> float:
        """Get biogenic carbon stock for a specific product type"""
        product_spec = self.product_manager.get_product_specification(product_type)
        return product_spec.biogenic_carbon_stock if product_spec else 0.0
