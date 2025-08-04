import numpy as np
from typing import Dict, Optional
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
from core.treatment_utils import (
    get_transformation_efficiency,
    calculate_output_amounts,
    update_waste_storage,
    fulfill_demand,
    track_treatment_properties,
    update_utilization_metrics
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
        self.demand = 0
        self.demand_history = []
        self.minimum_required_waste = 0.1
        self.production_history = []
        self._waste_storage = dict.fromkeys(WasteType, 0.0)
        self.total_products_created = 0.0
        self.processed_volumes = dict.fromkeys(WasteType, 0.0)
        self.product_volumes = {
            "mdf": 0.0,
            "particle_board": 0.0,
            "osb": 0.0
        }

        # Initialize product data manager for accessing product specifications
        self.product_manager = ProductDataManager()

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
        """Set waste storage with overflow detection"""
        if not isinstance(new_storage, dict):
            return
        
        # Check for overflow
        total_new = sum(new_storage.values())
        if total_new > self.waste_storage_capacity:
            overflow_amount = total_new - self.waste_storage_capacity
            handle_storage_event(
                self, 
                overflow_amount, 
                self.region
            )
            
            # Scale down proportionally
            scaling_factor = self.waste_storage_capacity / total_new
            self._waste_storage = {
                waste_type: amount * scaling_factor
                for waste_type, amount in new_storage.items()
            }
        else:
            self._waste_storage = dict(new_storage)

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
        
        forecasted_demand = self.calculate_realistic_demand()
        
        # PUSH maintains higher inventory with safety stock
        safety_multiplier = 1.2  # 20% safety stock 
        target_inventory = forecasted_demand * safety_multiplier
        current_total = sum(self.waste_storage.values())
        
        if current_total < target_inventory:
            collection_amount = target_inventory - current_total
            
            self.demand = collection_amount 
            self.trigger_collection()
        
        yield self.env.timeout(7.0)  # Weekly collection cycle

    def _pull_collection_logic(self, current_time):
        """PULL: Kanban-driven with signal propagation to collectors"""
        
        # Check for kanban signals
        active_signals = self.kanban_manager.get_signals(current_time)
        
        if active_signals:
            total_immediate_demand = len(active_signals) * 2.0
            
            self.demand = total_immediate_demand
            self.trigger_collection()
            self.kanban_manager.clear_signals()
            yield self.env.timeout(self.processing_time)
        else:
            # Monitor for low inventory AND propagate signals to collectors
            for waste_type, volume in self.waste_storage.items():
                if volume < 2.0:  # Low threshold for PULL
                    # Add signal to our own kanban manager
                    self.kanban_manager.add_signal(
                        waste_type=waste_type,
                        priority=5,
                        timestamp=current_time,
                        volume=volume,
                        source_id=self.name,
                        source_type="treatment"
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
                            priority=8,
                            timestamp=current_time,
                            volume=volume,
                            source_id=self.name,
                            source_type="treatment" 
                        )
            
            yield self.env.timeout(1.0)

    def calculate_realistic_demand(self) -> float:
        """Calculate realistic demand based on processing capacity and storage constraints"""
        
        current_total = sum(self.waste_storage.values())
        storage_utilization = current_total / self.waste_storage_capacity
        
        available_capacity = (self.waste_storage_capacity - current_total) * 0.8  # 80% fill max
        
        max_processable = self.processing_capacity * 3.0  # Max 3 processing cycles worth
        
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()
        total_unmet = sum(unmet_demands.values())
        
        if storage_utilization > 0.8:  
            urgency_factor = 0.3
        elif storage_utilization > 0.5:  
            urgency_factor = 0.7
        else:  
            urgency_factor = 1.0

        demand_cap = min(
            self.waste_storage_capacity * 0.1,
            self.processing_capacity * 0.5
        )

        base_demand = min(
            available_capacity,          
            max_processable,            
            total_unmet * 0.3,          
            demand_cap                   
        )
        realistic_demand = base_demand * urgency_factor
        
        return max(realistic_demand, 0.0)
            
    def _get_prioritized_transformations(self):
        """Get transformations sorted by priority based on current demands and system state"""
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

    def _handle_failures(self, current_time: float):
        """Checks for and handles facility failures, updating processing capacity."""
        if not (self.uncertainty_set and hasattr(self.uncertainty_set, 'treatment_failure')):
            return

        is_failed = self.check_failure(current_time, self.uncertainty_set.treatment_failure.probability)
        was_failed = getattr(self, '_was_failed', False)

        if is_failed and self.status == EntityStatus.FAILED:
            self.processing_capacity = self.initial_processing_capacity * 0.3
        elif not is_failed and self.status == EntityStatus.OPERATIONAL and was_failed:
            self.processing_capacity = self.initial_processing_capacity * 0.8

        self._was_failed = (self.status == EntityStatus.FAILED)

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

        amount_to_process = min(self.waste_storage[input_type], self.processing_capacity)
        
        if amount_to_process <= 0:
            return
        
        efficiency = min(get_transformation_efficiency(self, transformation), 1.0)
        
        amount_to_process, output_amount = calculate_output_amounts(
            amount_to_process, 
            efficiency
        )
        
        update_waste_storage(self, input_type, output_type, amount_to_process, output_amount)
        
        if output_type in final_products:
            # First, fulfill demand using product_to_sell storage
            total_to_sell_stored = sum(self.product_to_sell.current_storage.values())
            to_sell_capacity = self.product_to_sell.capacity
            addable_to_sell = min(output_amount, to_sell_capacity - total_to_sell_stored)
            overflow_after_sell = output_amount - addable_to_sell
            self.product_to_sell.current_storage[output_type] += addable_to_sell

            # Fulfill demand and track in simulation state
            if addable_to_sell > 0:
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
            return  
        
        # Track processing costs
        track_treatment_properties(self, amount_to_process, transformation)
        
        # Update utilization metrics
        update_utilization_metrics(self, amount_to_process)

    def request_waste_directly(self, required_waste: float, input_waste_types: set) -> Dict[WasteType, float]:
        """Request waste with realistic 80% local / 20% cross-region routing"""
        collected_waste = {}
        local_portion = required_waste * 0.8
        cross_region_portion = required_waste * 0.2

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
        state = SimulationState.get_instance()
        
        product_demands = {}
        
        for product_type in [OutputType.MDF, OutputType.PARTICLE_BOARD, OutputType.OSB]:
            key = product_type.value.lower().replace('_', '_') 
            if key in state.target_demands and key in state.total_products:
                unmet_demand = state.target_demands[key] - state.total_products[key]
                if unmet_demand > 0:
                    product_demands[product_type] = unmet_demand
        
        self.demand = sum(product_demands.values())
        
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
