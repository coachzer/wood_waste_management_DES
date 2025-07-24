import numpy as np
from typing import Dict, List
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES
from typing import Optional
from utils.capacity_utils import handle_overflow_with_decision, check_storage_capacity
from core.kanban_manager import KanbanManager
from core.collector_utils import (
    handle_completed_transport,
    check_completed_transports,
    handle_collector_capacity,
    get_prioritized_generators
)

class CollectorCompany(OperationalEntity):
    @property
    def waste_storage_capacity(self):
        """Expose collection center's waste_storage_capacity for compatibility."""
        return self.collection_center.waste_storage_capacity

    @waste_storage_capacity.setter
    def waste_storage_capacity(self, value):
        self.collection_center.waste_storage_capacity = value
    
    """A company that collects waste from generators"""

    def __init__(
        self,
        env,
        name,
        waste_types,
        collection_capacity,
        collection_frequency,
        transport_cost,
        environmental_impact,
        efficiency,
        availability=True,
        region=None,
        num_vehicles: int = 3,
        vehicle_capacity: Optional[float] = None,
        uncertainty_set = None,
        kanban_manager: KanbanManager = None,
        inventory_policy: InventoryPolicy = InventoryPolicy.PUSH,
        stock_strategy: StockStrategy = StockStrategy.REORDER_90,
        transport_manager: PointToPointTransport = None
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.waste_types = set(waste_types) if waste_types else set()
        self.kanban_manager = kanban_manager or KanbanManager()
        self.inventory_policy = inventory_policy
        self.stock_strategy = stock_strategy
        self.transport_manager = transport_manager or PointToPointTransport()
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None
        self.uncertainty_set = uncertainty_set

        # Initialize collection center
        self.collection_center = CollectionCenter(
            region=self.region_type,  # Use enum for internal operations
            waste_storage_capacity=collection_capacity * 2,  # Double the collection capacity
            current_storage=dict.fromkeys(WasteType, 0.0),
            coordinates=(
                REGION_COORDINATES[self.region_type] if self.region_type else (0.0, 0.0)
            ),
        )

        self.vehicle_capacity = vehicle_capacity or collection_capacity
        self.vehicles = [
            Vehicle(
                id=f"{self.name}_vehicle_{i}",
                capacity=self.vehicle_capacity,
                current_region=self.region_type,
            )
            for i in range(num_vehicles)
        ]

        # Track active transports
        self.active_transports = []

        # Initialize waste tracking
        self.collected_waste = dict.fromkeys(WasteType, 0.0)

        self.waste_monitor = WasteMonitor()

        # Initialize RNG for collection adjustments
        self.rng = np.random.default_rng(42)  # For reproducibility

        # Start collection process
        self.process = env.process(self.collection_loop())
        self.transport_process = env.process(self.manage_transport())

    def manage_transport(self):
        """Transport management using point-to-point system"""
        while True:
            current_time = self.env.now
            
            try:
                # Process new transport requests
                new_transports = self.transport_manager.process_requests(current_time)
                self.active_transports.extend(new_transports)
                
                # Check completed transports
                completed = check_completed_transports(self.active_transports, current_time)
                
                for transport in completed:
                    handle_completed_transport(transport, current_time)
                    self.active_transports.remove(transport)
                    
            except Exception as e:
                print(f"Error in transport management: {str(e)}")
            
            yield self.env.timeout(1.0)

    def check_failure(self, current_time, failure_probability):
        """Check for failures based on probability"""
        if self.rng.random() < failure_probability:
            print(f"{current_time}: Collector {self.name} has failed")
            self.status = EntityStatus.FAILED
            self.failure_time = current_time
            self.recovery_time = current_time + self.rng.uniform(24, 72) # Recovery time: uniform between 24 and 72 days
            self.availability = False

    def collect_from_generator(self, generator):
        """Collect waste from a generator, handling multiple waste types"""
        if not self.availability:
            print(f"[DEBUG] Collector {self.name} is not available for collection.")
            return 0

        # Pre-filter active waste streams, only allow collector's waste_types
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0 and (waste_type in self.waste_types or (hasattr(waste_type, 'value') and waste_type.value in self.waste_types))
        }

        print(f"[DEBUG] Collector {self.name} active streams: {active_streams.keys()}")

        if not active_streams:
            print(f"[DEBUG] Collector {self.name}: No active waste streams to collect from generator {getattr(generator, 'name', str(generator))}.")
            return 0

        potential_collections = {}
        enum_to_original = {}  

        for waste_type_str, stream in active_streams.items():
            # Convert WasteType enum to string value if needed
            if isinstance(waste_type_str, WasteType):
                waste_type_value = waste_type_str.value
            else:
                waste_type_value = waste_type_str

            waste_type_enum = None

            mapping = {wt.value: wt for wt in WasteType}
            waste_type_enum = mapping.get(waste_type_value)
            if not waste_type_enum:
                print(f"[DEBUG] Warning: Invalid waste type {waste_type_value}")
                continue

            potential_collections[waste_type_enum] = min(
                stream.volume,
                self.collection_capacity * self.efficiency
            )
            enum_to_original[waste_type_enum] = waste_type_str

        # Check storage capacity constraints
        allowed_collections, overflow_amount = check_storage_capacity(
            self.collection_center.current_storage,
            potential_collections,
            self.collection_center.waste_storage_capacity
        )

        if overflow_amount > 0:
            _, strategy = handle_overflow_with_decision(
                self,
                overflow_amount,
                self.region
            )
            self.waste_monitor.track_overflow(
                "collector",
                overflow_amount,
                strategy,
                self.env.now,
                self.region
            )
            print(f"[DEBUG] Collector {self.name}: Overflow of {overflow_amount:.2f} m³ handled with strategy {strategy}.")

        # Process allowed collections
        total_collected = 0.0
        for waste_type_enum, amount in allowed_collections.items():
            if amount > 0:
                original_type = enum_to_original[waste_type_enum]
                # Update generator's waste stream using original string key
                active_streams[original_type].volume -= amount
                generator.current_storage -= amount

                # Track waste removal from generator's region
                SimulationState.get_instance().track_waste_collection(
                    generator.region, waste_type_enum, amount
                )

                # Update collection center storage and tracking
                self.collection_center.current_storage[waste_type_enum] += amount
                self.collected_waste[waste_type_enum] += amount

                # Track waste addition to collector's region
                SimulationState.get_instance().track_waste_generation(
                    self.region, waste_type_enum, amount
                )

                total_collected += amount
                print(f"[DEBUG] Collector {self.name} collected {amount:.2f} m³ of {waste_type_enum.value} from generator {getattr(generator, 'name', str(generator))}.")

        if total_collected > 0:
            generator.mark_collected()
            print(f"[DEBUG] Collector {self.name} finished collection from generator {getattr(generator, 'name', str(generator))}. Total collected: {total_collected:.2f} m³.")
            return self.transport_cost + (0.1 * total_collected)
        print(f"[DEBUG] Collector {self.name}: No waste collected from generator {getattr(generator, 'name', str(generator))}.")
        return 0

    def collect_with_collaboration(self, generator, other_collectors):
        """Collaborative collection handling multiple waste types"""
        # Consider collection center capacities
        remaining_capacity = {
            collector.name: min(
                collector.collection_capacity * collector.efficiency,
                collector.collection_center.waste_storage_capacity
                - sum(collector.collection_center.current_storage.values()),
            )
            for collector in [self] + other_collectors
        }

        active_streams = {}
        for waste_type_str, stream in generator.waste_streams.items():
            if stream.volume <= 0:
                continue
            
            normalized_type = waste_type_str.replace(" ", "_").replace("-", "_")
            try:
                waste_type_enum = WasteType[normalized_type]
            except KeyError:
                waste_type_mapping = {
                    "03_01_05": WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
                    "15_01_03": WasteType.WOODEN_PACKAGING_15_01_03,
                    "17_02_01": WasteType.CONSTRUCTION_WOOD_17_02_01,
                    "03_01_01": WasteType.BARK_WASTE_03_01_01,
                    "20_01_38": WasteType.NON_HAZARDOUS_WOOD_20_01_38,
                    "15_01_01": WasteType.PAPER_PACKAGING_15_01_01
                }
                waste_type_enum = waste_type_mapping.get(normalized_type)
                if waste_type_enum is None:
                    print(f"Warning: Invalid waste type {waste_type_str}")
                    continue
            
            active_streams[waste_type_enum] = stream

        if not active_streams:
            return

        available_collectors = [self] + [c for c in other_collectors if c.availability]
        if not available_collectors:
            return
            
        total_storage = sum(remaining_capacity.values())
        if total_storage <= 0:
            return

        total_cost = 0
        for waste_type, waste_stream in active_streams.items():
            for collector in available_collectors:
                capacity_ratio = remaining_capacity[collector.name] / total_storage
                target_volume = waste_stream.volume * capacity_ratio
                if target_volume > 0:
                    handle_collector_capacity(self,
                        collector, waste_type, target_volume, waste_stream, 
                        remaining_capacity, generator
                    )
                    total_cost += collector.transport_cost * target_volume

        return total_cost

    def collection_loop(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            current_time = self.env.now
            print(f"{current_time}: Collector {self.name} starting collection process")

            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)

            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            base_timeout = self.collection_frequency

            if self.inventory_policy == InventoryPolicy.PULL and self.kanban_manager.get_signals():
                print(f"{current_time}: Collector {self.name} has kanban signals, using base frequency")
                timeout = base_timeout
            else:
                print(f"{current_time}: Collector {self.name} no kanban signals, adjusting frequency")
                timeout = base_timeout + self.rng.uniform(1, 4)
            
            yield self.env.timeout(timeout)

            # Skip collection if failed or unavailable
            if self.status == EntityStatus.FAILED or not self.availability:
                print(f"{current_time}: Collector {self.name} is currently failed or unavailable, skipping collection")
                continue

            # Check for recovery
            if (self.status == EntityStatus.FAILED and 
                current_time >= self.recovery_time):
                print(f"{current_time}: Collector {self.name} has recovered from failure")
                self.status = EntityStatus.OPERATIONAL
                self.failure_time = None
                self.recovery_time = None
                self.availability = True

            if not self.should_collect():
                print(f"{current_time}: Collector {self.name} decided not to collect based on policy and strategy")
                continue

            kanban_signals = self.kanban_manager.get_signals()
            if kanban_signals and self.inventory_policy == InventoryPolicy.PULL:
                print(f"{current_time}: Collector {self.name} processing kanban signals")
                self._process_kanban_signals(kanban_signals)
                self.kanban_manager.clear_signals()
            else:
                # Regular collection based on policy
                print(f"{current_time}: Collector {self.name} performing unified collection strategy")
                prioritized_generators = get_prioritized_generators()
                collection_cost = self._unified_collection_strategy(prioritized_generators)
                
                if collection_cost > 0:
                    print(f"{self.env.now}: {self.name} collection cost: {collection_cost:.8f}")

    def _process_kanban_signals(self, signals):
        """Handle kanban signals for PULL policy"""
        for signal in signals:
            try:
                waste_type_enum = WasteType[signal['waste_type']]
            except KeyError:
                continue
                
            prioritized_generators = [
                g for g in get_prioritized_generators()
                if waste_type_enum in g.waste_streams and g.region == self.region
            ]
            
            for generator in prioritized_generators:
                self.collect_from_generator(generator)

    def should_collect(self) -> bool:
        current_utilization = sum(self.collection_center.current_storage.values()) / self.collection_center.waste_storage_capacity
        
        print(f"DEBUG: {self.name} - policy: {self.inventory_policy}, strategy: {self.stock_strategy}")
        
        if self.inventory_policy == InventoryPolicy.PULL:
            has_demand = bool(self.kanban_manager.get_signals())
            below_reorder = self._is_below_reorder_point(current_utilization)
            
            print(f"DEBUG: {self.name} - PULL policy: has_demand={has_demand}, below_reorder={below_reorder}, utilization={current_utilization}")
            print(f"DEBUG: {self.name} - should_collect result: {has_demand or below_reorder}")
            
            return has_demand or below_reorder
        
        elif self.inventory_policy == InventoryPolicy.PUSH:
            should_restock = self._should_restock(current_utilization)
            print(f"DEBUG: {self.name} - PUSH policy: should_restock={should_restock}, utilization={current_utilization}")
            return should_restock
        
        print(f"DEBUG: {self.name} - no policy matched, returning False")
        return False
    
    def _is_below_reorder_point(self, utilization: float) -> bool:
        """Check if we're below the reorder threshold"""
        if self.stock_strategy == StockStrategy.REORDER_90:
            return utilization < 0.90
        elif self.stock_strategy == StockStrategy.REORDER_50:
            return utilization < 0.50
        elif self.stock_strategy == StockStrategy.ON_DEMAND:
            return utilization < 0.10
        elif self.stock_strategy == StockStrategy.FULL_STOCK:
            return utilization < 0.95  
        return False

    def _should_restock(self, utilization: float) -> bool:
        """Check if we should restock (for PUSH policy)"""
        if self.stock_strategy == StockStrategy.FULL_STOCK:
            return utilization < 0.95  # Keep nearly full
        elif self.stock_strategy == StockStrategy.REORDER_90:
            return utilization < 0.90
        elif self.stock_strategy == StockStrategy.REORDER_50:
            return utilization < 0.50
        elif self.stock_strategy == StockStrategy.ON_DEMAND:
            return False  # Never proactively restock
        return False

    def transfer_waste_to_region(self, waste_type: WasteType, volume: float, destination: RegionType) -> bool:
        """Updated method using point-to-point transport"""
        if volume <= 0:
            print(f"{self.env.now}: {self.name} attempted to transfer zero or negative volume of {waste_type.value}")
            return False
        
        # Create transport request
        request = TransportRequest(
            origin=self.region_type,
            destination=destination,
            waste_type=waste_type,
            volume=volume,
            priority=TransportPriority.NORMAL,
            request_time=self.env.now,
            requester_id=self.name
        )
        
        # Submit request to transport manager
        success = self.transport_manager.request_transport(request)
        
        if success:
            # Remove from our storage immediately (it's now "in transit")
            if self.collection_center.current_storage[waste_type] >= volume:
                self.collection_center.current_storage[waste_type] -= volume
                print(f"{self.env.now}: {self.name} scheduled transport of {volume:.2f} m³ {waste_type.value}")
                return True
        
        return False

    def _unified_collection_strategy(self, prioritized_generators: List) -> float:
        """Unified collection strategy that considers both efficiency and collaboration"""
        state = SimulationState.get_instance()
        
        # Get other available collectors in the region for load balancing
        other_collectors = [
            c for c in state.collectors 
            if c != self and c.availability and c.region_type == self.region_type
        ]
        
        total_cost = 0
        
        for generator in prioritized_generators:
            if generator.current_storage <= 0:
                continue
                
            # Check if we have capacity and other collectors are overloaded
            our_utilization = sum(self.collection_center.current_storage.values()) / self.collection_center.waste_storage_capacity
            
            if our_utilization < 0.8:  # We have capacity
                # Collect directly
                cost = self.collect_from_generator(generator)
                total_cost += cost
            elif other_collectors:
                # Find least utilized collector for collaboration
                least_utilized = min(other_collectors, 
                    key=lambda c: sum(c.collection_center.current_storage.values()) / c.collection_center.waste_storage_capacity)
                
                if sum(least_utilized.collection_center.current_storage.values()) / least_utilized.collection_center.waste_storage_capacity < 0.8:
                    # Collaborate with least utilized collector
                    cost = self.collect_with_collaboration(generator, [least_utilized])
                    total_cost += cost
            
        return total_cost

    def provide_waste_for_treatment(self, requested_amount: float, needed_types: set) -> Dict[WasteType, float]:
    
        provided_waste = {}
        remaining_request = requested_amount

        # ONLY provide from storage - no direct collection
        for waste_type in needed_types:
            if remaining_request <= 0:
                break
                
            available_in_storage = self.collection_center.current_storage[waste_type]
            if available_in_storage > 0:
                transfer_amount = min(available_in_storage, remaining_request)
                
                self.collection_center.current_storage[waste_type] -= transfer_amount
                provided_waste[waste_type] = provided_waste.get(waste_type, 0) + transfer_amount
                remaining_request -= transfer_amount
                
                print(f"Transferred {transfer_amount:.2f} m³ of {waste_type} from storage")
        
        # If we can't fulfill the request, that's okay - treatment will have to wait
        total_provided = sum(provided_waste.values())
        if total_provided < requested_amount:
            shortfall = requested_amount - total_provided
            print(f"Collector {self.name} storage insufficient: requested {requested_amount:.2f} m³, "
                f"provided {total_provided:.2f} m³, shortfall {shortfall:.2f} m³")
        
        return provided_waste