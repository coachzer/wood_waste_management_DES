import numpy as np
from typing import Dict, Iterable, Optional
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from config.base_config import get_scenario_config
from models.data_classes import WasteTransformation, OperationalEntity, ProductStorage
from models.distances import get_distance
from models.enums import OutputType, RegionType, StockStrategy, WasteType, EntityStatus
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from core.kanban_manager import KanbanManager
from models.enums import InventoryPolicy
from core.treatment_utils import (
    get_transformation_efficiency,
    calculate_output_amounts,
    update_waste_storage,
    fulfill_demand,
    track_treatment_properties,
    update_utilization_metrics,
    calculate_required_waste
)

from utils.capacity_utils import apply_capacity_constraints, apply_partial_update_with_constraints, handle_overflow_with_decision, check_storage_capacity

class StorageDict(dict):
    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        excluded_keys = {key}
        result = apply_capacity_constraints(
            sum(v for k, v in self.items() if k not in excluded_keys),
            value,
            self.owner.waste_storage_capacity
        )
        if result.overflow_amount > 0:
            _, strategy = handle_overflow_with_decision(
                self.owner,
                result.overflow_amount,
                self.owner.region
            )
            self.owner.waste_monitor.track_overflow(
                facility_type="treatment",
                volume=result.overflow_amount,
                strategy=strategy,
                timestamp=self.owner.env.now,
                region=self.owner.region
            )
        super().__setitem__(key, result.allowed_amount)

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
        product_storage_capacity: float = 0.0,
        product_to_sell_capacity: float = 0.0,
        scenario_config=None,
        stock_strategy: StockStrategy = None,
        inventory_policy: InventoryPolicy = None,
        transport_manager: Optional[PointToPointTransport] = None
    ):
        super().__init__()

        self.waste_monitor = waste_monitor
        self.stock_strategy = stock_strategy
        self.inventory_policy = inventory_policy

        if waste_monitor is None:
            raise ValueError("waste_monitor is required for TreatmentOperator")
        
        if scenario_config and hasattr(scenario_config, 'inventory_policy'):
            self.inventory_policy = scenario_config.inventory_policy
        else:
            self.inventory_policy = get_scenario_config().inventory_policy

        self.kanban_manager = kanban_manager or KanbanManager()
        self.transport_manager = transport_manager or PointToPointTransport()
        self.env = env
        self.name = name
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
        self.demand = 0
        self.demand_history = []
        self.minimum_required_waste = 0.1
        self.production_history = []
        self._waste_storage = StorageDict(self, dict.fromkeys(WasteType, 0.0))
        self.total_products_created = 0.0
        self.processed_volumes = dict.fromkeys(WasteType, 0.0)
        self.product_volumes = {
            "mdf": 0.0,
            "particle_board": 0.0,
            "osb": 0.0
        }

        # Product storage
        self.product_storage_capacity = product_storage_capacity
        self.product_to_sell_capacity = product_to_sell_capacity
        self.product_storage = ProductStorage(
            capacity=self.product_storage_capacity,
            current_storage=dict.fromkeys(OutputType, 0.0)
        )
        self.product_to_sell = ProductStorage(
            capacity=self.product_to_sell_capacity,
            current_storage=dict.fromkeys(OutputType, 0.0)
        )

        # Stochastic components
        self.uncertainty_set = uncertainty_set
        self.rng = np.random.default_rng(42)
        self.transformation_efficiency = 0.95
        if self.uncertainty_set and hasattr(self.uncertainty_set, 'treatment_failure'):
            self.failure_check_interval = self.uncertainty_set.treatment_failure.check_interval

        # Transformations
        self.transformations = transformations or self._default_transformations()

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
        """Set waste storage with capacity constraints"""
        if not isinstance(new_storage, dict):
            return
        
        if len(new_storage) == len(self._waste_storage):
            self._handle_full_storage_update(new_storage)
        else:
            self._handle_partial_storage_update(new_storage)

    def _handle_full_storage_update(self, new_storage: Dict[WasteType, float]) -> None:
        """Update all storage values while respecting capacity constraints"""
        result = apply_partial_update_with_constraints(
            current_values=self._waste_storage,
            updates=new_storage,
            capacity=self.waste_storage_capacity
        )
        if result.overflow_amount > 0:
            _, strategy = handle_overflow_with_decision(
                self,
                result.overflow_amount,
                self.region
            )
            self.waste_monitor.track_overflow(
                facility_type="treatment",
                volume=result.overflow_amount,
                strategy=strategy,
                timestamp=self.env.now,
                region=self.region
            )
        self._waste_storage = StorageDict(self, result.scaled_values)

    def _handle_partial_storage_update(self, partial_update: Dict[WasteType, float]) -> None:
        """Update specific storage values while respecting capacity constraints"""
        result = apply_partial_update_with_constraints(
            current_values=self._waste_storage,
            updates=partial_update,
            capacity=self.waste_storage_capacity,
            excluded_keys=set(partial_update.keys())
        )
        if result.overflow_amount > 0:
            _, strategy = handle_overflow_with_decision(
                self,
                result.overflow_amount,
                self.region
            )
            self.waste_monitor.track_overflow(
                facility_type="treatment",
                volume=result.overflow_amount,
                strategy=strategy,
                timestamp=self.env.now,
                region=self.region
            )
        for waste_type, amount in result.scaled_values.items():
            self._waste_storage[waste_type] = amount

    def _calculate_current_total_excluding(self, waste_types_to_exclude: Iterable[WasteType]) -> float:
        """Calculate current storage total excluding specified waste types"""
        return sum(
            amount for wtype, amount in self._waste_storage.items() 
            if wtype not in waste_types_to_exclude
        )

    def _apply_partial_update_without_overflow(self, partial_update: Dict[WasteType, float]) -> None:
        """Apply partial update when there's no capacity overflow"""
        for waste_type, amount in partial_update.items():
            self._waste_storage[waste_type] = amount

    def _apply_partial_update_with_scaling(self, partial_update: Dict[WasteType, float], scaling_factor: float) -> None:
        """Apply partial update with scaling to avoid overflow"""
        for waste_type, amount in partial_update.items():
            scaled_amount = amount * scaling_factor
            self._waste_storage[waste_type] = scaled_amount
            overflow_amount = amount - scaled_amount
            if overflow_amount > 0:
                self.waste_monitor.track_overflow(
                    facility_type="treatment",
                    volume=overflow_amount,
                    strategy="landfill",
                    timestamp=self.env.now,
                    region=self.region
                )

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
        """PUSH: Forecast-based with startup protection"""
        
        # Calculate forecast 
        forecasted_demand = self._calculate_demand_forecast()
        
        # PUSH maintains higher inventory with safety stock
        safety_multiplier = 1.6  # 60% safety stock for PUSH
        target_inventory = forecasted_demand
        current_total = sum(self.waste_storage.values())
        
        if current_total < target_inventory:
            collection_amount = target_inventory - current_total
            print(f"[PUSH] Forecast: {forecasted_demand:.1f}, target: {target_inventory:.1f}, "
                f"current: {current_total:.1f}, collecting: {collection_amount:.1f}")
            
            self.demand = collection_amount 
            self.trigger_collection()
        
        yield self.env.timeout(7.0)  # Weekly collection cycle

    def _pull_collection_logic(self, current_time):
        """PULL: Kanban-driven with signal propagation to collectors"""
        
        # Check for kanban signals
        active_signals = self.kanban_manager.get_signals()
        
        if active_signals:
            total_immediate_demand = len(active_signals) * 2.0
            print(f"[PULL] {len(active_signals)} kanban signals, demand: {total_immediate_demand:.1f}")
            
            self.demand = total_immediate_demand
            self.trigger_collection()
            self.kanban_manager.clear_signals()
            yield self.env.timeout(self.processing_time)
        else:
            # Monitor for low inventory AND propagate signals to collectors
            for waste_type, volume in self.waste_storage.items():
                print(f"[PULL MONITOR] {waste_type.value}: {volume:.1f} m³ in storage")
                if volume < 2.0:  # Low threshold for PULL
                    # Add signal to our own kanban manager
                    self.kanban_manager.add_signal(
                        waste_type=waste_type,
                        priority=5,
                        timestamp=current_time
                    )
                    
                    # ALSO propagate to collectors in our region
                    state = SimulationState.get_instance()
                    local_collectors = [
                        c for c in state.collectors 
                        if c.region_type == self.region_type and c.inventory_policy == InventoryPolicy.PULL
                    ]
                    
                    for collector in local_collectors:
                        collector.kanban_manager.add_signal(
                            waste_type=waste_type,
                            priority=8,  # High priority for collectors
                            timestamp=current_time
                        )
                        print(f"[KANBAN PROPAGATION] Signal sent to {collector.name} for {waste_type.value}")
            
            yield self.env.timeout(1.0)
                
    def _calculate_demand_forecast(self) -> float:
        """PUSH-specific: Calculate forecasted demand with safe fallbacks"""
        
        # Fallback 1: No history at all
        if not self.demand_history:
            fallback_demand = max(self.demand, 10.0) if hasattr(self, 'demand') else 10.0
            print(f"[FORECAST] No history, using fallback: {fallback_demand:.1f}")
            return fallback_demand
        
        # Fallback 2: Very limited history (< 3 data points)
        if len(self.demand_history) < 3:
            simple_avg = sum(d for _, d in self.demand_history) / len(self.demand_history)
            print(f"[FORECAST] Limited history ({len(self.demand_history)} points), using average: {simple_avg:.1f}")
            return max(simple_avg, 1.0)
        
        # Normal case: Sufficient history for exponential smoothing
        recent_demands = [d for _, d in self.demand_history[-8:]]  # Safe now
        
        try:
            # Exponential smoothing with error handling
            alpha = 0.3
            forecast = recent_demands[0]
            
            for demand in recent_demands[1:]:
                forecast = alpha * demand + (1 - alpha) * forecast
            
            # Add trend component if we have enough data
            if len(recent_demands) >= 4:
                recent_trend = (recent_demands[-1] - recent_demands[-4]) / 3
                forecast += recent_trend
            
            result = max(forecast, 1.0)  # Never forecast negative
            print(f"[FORECAST] Exponential smoothing: {result:.1f} (from {len(recent_demands)} points)")
            return result
            
        except (IndexError, ZeroDivisionError, TypeError) as e:
            # Emergency fallback
            backup = sum(recent_demands) / len(recent_demands) if recent_demands else 10.0
            print(f"[FORECAST] Error in calculation ({e}), using backup: {backup:.1f}")
            return max(backup, 1.0)
            
    def _get_prioritized_transformations(self):
        """Get transformations sorted by priority based on current demands and system state"""
        # Get current demands and state
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()
        
        # Check if any demands are still unmet
        if any(demand > 0 for demand in unmet_demands.values()):
            # Still have unmet demands - prioritize based on remaining demand
            product_demands = {
                OutputType.MDF: unmet_demands.get('mdf', 0),
                OutputType.PARTICLE_BOARD: unmet_demands.get('particle_board', 0),
                OutputType.OSB: unmet_demands.get('osb', 0)
            }
            
            # Sort transformations by unmet demand and efficiency
            return sorted(
                self.transformations.items(),
                key=lambda x, demands=product_demands: (
                    # Primary sort: Has unmet demand
                    demands.get(x[0][1], 0) > 0,
                    # Secondary sort: Amount of unmet demand
                    demands.get(x[0][1], 0),
                    # Tertiary sort: Efficiency
                    get_transformation_efficiency(self, x[1])
                ),
                reverse=True
            )
        else:
            # All demands met - sort based on transformation efficiency
            return sorted(
                self.transformations.items(),
                key=lambda x: get_transformation_efficiency(self, x[1]),
                reverse=True
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

    def run_facility(self):
        """Main process loop for the treatment facility"""
        while True:
            current_time = self.env.now
            
            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'treatment_failure'):
                is_failed = self.check_failure(current_time, self.uncertainty_set.treatment_failure.probability)
                
                # Handle efficiency changes when failure status changes
                if is_failed and self.status == EntityStatus.FAILED:
                    # Just became failed - reduce processing capacity
                    self.processing_capacity = self.initial_processing_capacity * 0.3  # Reduced capacity during failure
                elif not is_failed and self.status == EntityStatus.OPERATIONAL:
                    # Just recovered - restore processing capacity
                    if hasattr(self, '_was_failed') and self._was_failed:
                        self.processing_capacity = self.initial_processing_capacity * 0.8  # Gradual recovery
                
                # Track previous failure state
                self._was_failed = (self.status == EntityStatus.FAILED)
            
            # Skip processing if failed
            if self.status == EntityStatus.FAILED:
                print(f"{current_time}: Treatment operator {self.name} is currently failed, skipping processing")
                yield self.env.timeout(self.processing_time)
                continue

            # Get sorted transformations by priority
            sorted_transformations = self._get_prioritized_transformations()

            # Process transformations in priority order
            for (input_type, output_type), transformation in sorted_transformations:
                if self.waste_storage[input_type] > 0:
                    self._process_waste_transformation(input_type, output_type, transformation)

            # Wait for processing time before next cycle
            yield self.env.timeout(self.processing_time)
            
    def _process_waste_transformation(self, input_type, output_type, transformation):
        """Process a single waste transformation"""
        
        # Skip processing if input type is already a final product
        final_products = {
            OutputType.MDF,
            OutputType.PARTICLE_BOARD,
            OutputType.OSB
        }
        if input_type in final_products:
            # print("[PROCESS DEBUG] Skipping - input is already a final product")
            return

        # Process normally since we don't handle furniture anymore
        amount_to_process = min(self.waste_storage[input_type], self.processing_capacity)
        
        if amount_to_process <= 0:
            # print("[PROCESS DEBUG] No waste to process")
            return
        
        # Get transformation efficiency with uncertainty
        efficiency = min(get_transformation_efficiency(self, transformation), 1.0)
        
        # Calculate output and handle capacity constraints
        amount_to_process, output_amount = calculate_output_amounts(
            amount_to_process, 
            efficiency
        )
        
        # Update waste storage and tracking
        update_waste_storage(self, input_type, output_type, amount_to_process, output_amount)
        
        # Handle demand fulfillment for final products
        if output_type in final_products:
            # First, fulfill demand using product_to_sell storage
            total_to_sell_stored = sum(self.product_to_sell.current_storage.values())
            to_sell_capacity = self.product_to_sell.capacity
            addable_to_sell = min(output_amount, to_sell_capacity - total_to_sell_stored)
            overflow_after_sell = output_amount - addable_to_sell
            self.product_to_sell.current_storage[output_type] += addable_to_sell

            # Fulfill demand and track in simulation state
            if addable_to_sell > 0:
                # print(f"[PROCESS DEBUG] About to call fulfill_demand with {addable_to_sell:.2f} m³")
                fulfill_demand(self, output_type, addable_to_sell)

            # Any excess product goes to product_storage (no buyer)
            if overflow_after_sell > 0:
                total_stored = sum(self.product_storage.current_storage.values())
                storage_capacity = self.product_storage.capacity
                addable_to_storage = min(overflow_after_sell, storage_capacity - total_stored)
                # No further action needed for overflow_storage
                self.product_storage.current_storage[output_type] += addable_to_storage
                # If overflow_storage > 0, optionally log or handle further overflow

            # Track product volumes
            if output_type == OutputType.MDF:
                self.product_volumes["mdf"] += output_amount
            elif output_type == OutputType.PARTICLE_BOARD:
                self.product_volumes["particle_board"] += output_amount
            elif output_type == OutputType.OSB:
                self.product_volumes["osb"] += output_amount
        else:
            return  # Not a final product, no demand fulfillment needed
            # print("[PROCESS DEBUG] Output is not final product, skipping fulfillment")
        
        # Track processing costs
        track_treatment_properties(self, amount_to_process, transformation)
        
        # Update utilization metrics
        update_utilization_metrics(self, amount_to_process)

    def request_waste_directly(self, required_waste: float, input_waste_types: set) -> Dict[WasteType, float]:
        """Request waste with realistic 80% local / 20% cross-region routing"""
        state = SimulationState.get_instance()
        collected_waste = {}
        
        # Split demand: 80% local priority, 20% cross-region
        local_portion = required_waste * 0.8
        cross_region_portion = required_waste * 0.2
        
        print(f"[REALISTIC ROUTING] {self.name}: {local_portion:.1f} m³ local, {cross_region_portion:.1f} m³ cross-region")
        
        # 1. FIRST: Collect from local region (priority)
        remaining_local = local_portion
        local_collectors = [
            c for c in state.collectors 
            if c.region_type == self.region_type and c.availability
        ]
        
        for collector in local_collectors:
            if remaining_local <= 0:
                break
                
            print(f"[LOCAL COLLECTION] Requesting {remaining_local:.1f} m³ from {collector.name}")
            local_collected = collector.provide_waste_for_treatment(remaining_local, input_waste_types)
            
            # Add to total collected waste
            for waste_type, amount in local_collected.items():
                collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                remaining_local -= amount
                print(f"[LOCAL SUCCESS] Collected {amount:.1f} m³ of {waste_type.value}")
        
        # 2. SECOND: Cross-region collection via transport
        remaining_cross_region = cross_region_portion
        if remaining_cross_region > 0:
            
            remote_collectors = [
                c for c in state.collectors 
                if c.region_type != self.region_type and c.availability
            ]
            
            # Sort by distance (nearest first) instead of random shuffle
            remote_collectors.sort(key=lambda c: get_distance(self.region_type, c.region_type))
            
            for collector in remote_collectors[:3]:  # Try up to 3 nearest collectors
                if remaining_cross_region <= 0:
                    break
                    
                distance = get_distance(self.region_type, collector.region_type)
                print(f"[CROSS-REGION] Requesting {remaining_cross_region:.1f} m³ from {collector.name} ({collector.region}) - {distance:.1f}km away")
                
                # Use transport system!
                transport_collected = self._request_via_transport(
                    collector, remaining_cross_region, input_waste_types
                )
                
                # Add to total collected waste
                for waste_type, amount in transport_collected.items():
                    collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                    remaining_cross_region -= amount
        
        # 3. If we still need more, try any available collector (fallback)
        total_remaining = remaining_local + remaining_cross_region
        if total_remaining > 0:
            print(f"[FALLBACK] Still need {total_remaining:.1f} m³, trying any available collector")
            all_collectors = [c for c in state.collectors if c.availability]
            
            for collector in all_collectors:
                if total_remaining <= 0:
                    break
                fallback_collected = collector.provide_waste_for_treatment(total_remaining, input_waste_types)
                for waste_type, amount in fallback_collected.items():
                    collected_waste[waste_type] = collected_waste.get(waste_type, 0) + amount
                    total_remaining -= amount

        return collected_waste
    
    def _request_via_transport(self, collector, amount: float, waste_types: set) -> Dict[WasteType, float]:
        """Request waste via transport system"""
        print(f"[TRANSPORT REQUEST] Initiating transport from {collector.region} to {self.region}")
        
        # Get available waste from remote collector
        available_waste = self._get_available_waste_from_collector(collector, amount, waste_types)
        
        transported_waste = {}
        for waste_type, volume in available_waste.items():
            if volume > 0:
                print(f"[TRANSPORT] Attempting to transport {volume:.1f} m³ of {waste_type.value}")
                
                # Use the transport system!
                success = collector.transfer_waste_to_region(
                    waste_type, volume, self.region_type
                )
                
                if success:
                    transported_waste[waste_type] = volume
                    print(f"[TRANSPORT SUCCESS] {volume:.1f} m³ {waste_type.value} scheduled for transport")
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
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        
        product_demands = {}
        
        for product_type in [OutputType.MDF, OutputType.PARTICLE_BOARD, OutputType.OSB]:
            key = product_type.value.lower().replace('_', '_') 
            if key in state.target_demands and key in state.total_products:
                unmet_demand = state.target_demands[key] - state.total_products[key]
                if unmet_demand > 0:
                    product_demands[product_type] = unmet_demand
        
        # Update self.demand to include all unmet product demands
        self.demand = sum(product_demands.values())
        
        required_waste = calculate_required_waste(self)
        if required_waste <= 0:
            return 0, 0

        # Get all input types from transformations
        input_waste_types = {key[0] for key in self.transformations.keys()}
        
        # Request collection through coordinator
        collected_waste = self.request_waste_directly(required_waste, input_waste_types)

        # Validate collection result
        if not collected_waste or sum(collected_waste.values()) == 0:
            # print(f"[VALIDATION] No waste collected at time {self.env.now} - skipping processing")
            return 0, 0

        # Track this collection's demand
        self.demand_history.append((self.env.now, required_waste))
        self.waste_monitor.track_processing(self, self.env.now)

        # Add to storage with validation
        actually_stored = self._add_to_storage(collected_waste)
        if actually_stored == 0:
            print(f"[VALIDATION] Failed to store any collected waste at time {self.env.now}")
        if actually_stored < sum(collected_waste.values()):
            print(
                f"Could only store {actually_stored:.12f} m³ due to capacity constraints"
            )
            # Track overflow through data collector
            overflow_amount = sum(collected_waste.values()) - actually_stored
            self.waste_monitor.track_overflow(
                "treatment",
                overflow_amount,
                "landfill",  
                self.env.now,
                self.region
            )

        return actually_stored, sum(collected_waste.values())

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        # Transformation efficiencies from behavior model
        base_transformations = {
            # Construction and wood materials
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),   # High quality wood
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95),     # Good for recycling
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),  # Great for compression molding
            
            # Processing materials
            WasteType.BARK_WASTE_03_01_01: (0.85, 0.70),          # Good for boards
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),  # General recycling
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),      # Paper recycling
        }

        # Initialize empty transformations dictionary
        transformations = {}

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            # Construction wood waste (17 02 01) - Primary reuse pathways
            WasteType.CONSTRUCTION_WOOD_17_02_01: [
                OutputType.PARTICLE_BOARD,    # Downcycling pathway
                OutputType.OSB,    # OSB from construction wood
            ],
            
            # Sawdust, shavings, cuttings (03 01 05) - Primary particleboard feedstock
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: [
                OutputType.PARTICLE_BOARD,    # Primary pathway - supported by research
                OutputType.MDF,    # Secondary pathway
                OutputType.OSB,    # OSB from wood cuttings
            ],
            
            # Wooden packaging waste (15 01 03) - Cascading use
            WasteType.WOODEN_PACKAGING_15_01_03: [
                OutputType.PARTICLE_BOARD,    # Recycling pathway
                OutputType.OSB,    # OSB from packaging wood
            ],
            
            # Bark waste (03 01 01) - Limited applications
            WasteType.BARK_WASTE_03_01_01: [
                OutputType.MDF,    # Can incorporate bark content
                OutputType.PARTICLE_BOARD,    # Lower percentage incorporation
            ],
            
            # Non-hazardous wood (20 01 38) - Municipal waste stream
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: [
                OutputType.PARTICLE_BOARD,    # Primary recycling pathway
                OutputType.MDF,    # Secondary pathway
                OutputType.OSB,    # OSB from municipal wood
            ],
            
            # Paper packaging (15 01 01) - Paper cycle
            WasteType.PAPER_PACKAGING_15_01_01: [
                OutputType.MDF,    # Can incorporate recycled paper
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
            _, strategy = handle_overflow_with_decision(
                self,
                overflow_amount,
                self.region
            )
            self.waste_monitor.track_overflow(
                facility_type="treatment",
                volume=overflow_amount,
                strategy=strategy,
                timestamp=self.env.now,
                region=self.region
            )

        total_added = 0.0
        for waste_type, amount in allowed_additions.items():
            self.waste_storage[waste_type] += amount
            total_added += amount

        return total_added
