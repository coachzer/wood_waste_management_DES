import numpy as np
from typing import Dict
from config.constants import TRANSPORT_EMISSIONS_PER_M3_KM
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES, get_distance
from typing import Optional
from utils.capacity_utils import handle_storage_event, check_storage_capacity
from core.kanban_manager import KanbanManager
from core.collector_utils import (
    calculate_efficiency_multiplier,
    calculate_utilization,
    filter_active_waste_streams,
    get_adaptive_threshold,
    handle_completed_transport,
    check_completed_transports,
    get_prioritized_generators
)

class CollectorCompany(OperationalEntity):
    """A company that collects waste from generators"""

    @property
    def waste_storage_capacity(self):
        return self.collection_center.waste_storage_capacity

    @waste_storage_capacity.setter
    def waste_storage_capacity(self, value):
        self.collection_center.waste_storage_capacity = value
    
    @property
    def availability(self):
        """Map status to availability for backward compatibility"""
        return self.status == EntityStatus.OPERATIONAL
    
    @availability.setter  
    def availability(self, value):
        """Allow setting availability for backward compatibility"""
        self.status = EntityStatus.OPERATIONAL if value else EntityStatus.FAILED

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
        waste_monitor: Optional[WasteMonitor] = None,
        kanban_manager: KanbanManager = None,
        inventory_policy: InventoryPolicy = None,
        stock_strategy: StockStrategy = None,
        transport_manager: PointToPointTransport = None
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.facility_type = "collector"
        self.expansion_count = 0    
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

        self.collection_center = CollectionCenter(
            region=self.region_type, 
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
                capacity=self.vehicle_capacity, # m³
                current_region=self.region_type,
            )
            for i in range(num_vehicles)
        ]

        self.active_transports = []

        self.collected_waste = dict.fromkeys(WasteType, 0.0)

        self.waste_monitor = waste_monitor
        if waste_monitor is None:
            raise ValueError("waste_monitor is required for TreatmentOperator")

        self.rng = np.random.default_rng(42)

        self.process = env.process(self.collection_loop())
        self.transport_process = env.process(self.manage_transport())

    def _find_available_vehicle(self):
        """Find an available vehicle for collection"""
        return next((v for v in self.vehicles if not v.in_transit), None)

    def _calculate_travel_time_to_generator(self, generator):
        """Calculate travel time to generator (simplified)"""
        
        if generator.region_type == self.region_type:
            # Same region: assume 10-30km average within region
            base_distance = 10.0  # km average within region
            distance_variation = self.rng.uniform(0.5, 1.5)  # 10-30km range
            distance = base_distance * distance_variation
        else:
            # Different region: use full inter-region distance
            distance = get_distance(self.region_type, generator.region_type)
        
        travel_time_hours = distance / 40.0  
        travel_time_days = travel_time_hours / 24.0 
        return travel_time_days, distance

    def _dispatch_vehicle_for_collection(self, vehicle, generator, target_volume):
        """Complete vehicle collection process with proper storage and overflow handling"""
        current_time = self.env.now
        
        travel_time, distance = self._calculate_travel_time_to_generator(generator)
        
        vehicle.in_transit = True
        vehicle.destination = generator.region_type
        vehicle.estimated_arrival = current_time + travel_time
        
        yield self.env.timeout(travel_time)
        
        collected_amount, collected_waste = self._perform_collection_at_site(generator, target_volume)
        
        if collected_amount > 0:
            
            volume_cost_factor = 0.1
            vehicle.current_load = collected_amount
            yield self.env.timeout(travel_time)
            
            self._add_to_collection_center(collected_waste)
            collection_cost = self.transport_cost + (distance * volume_cost_factor * collected_amount)
                
            # Calculate transport emissions (convert m³ to tonnes using density, then multiply by distance and emissions factor)
            emissions = collected_amount * distance * TRANSPORT_EMISSIONS_PER_M3_KM

            if hasattr(self, 'waste_monitor') and self.waste_monitor:
                self.waste_monitor.update_entity_costs(
                    entity_name=self.name,
                    entity_type=self.facility_type,
                    energy_cost=0.0,
                    processing_cost=0.0,
                    transport_cost=collection_cost
                )
                self.waste_monitor.track_environmental_impact(
                    entity_name=self.name,
                    entity_type=self.facility_type,
                    environmental_impact=emissions,
                    timestamp=self.env.now,
                    impact_category="transport_emissions"
                )
        else:
            yield self.env.timeout(travel_time)
            collection_cost = self.transport_cost  
        
        # Vehicle is now available again
        vehicle.in_transit = False
        vehicle.current_load = 0
        vehicle.destination = self.region_type  
        
        return collection_cost

    def _perform_collection_at_site(self, generator, target_volume):# -> tuple[Literal[0], dict] | tuple[float | Literal[0], dict]:
        """Perform actual waste collection at generator site with proper constraint checking"""
        active_streams = filter_active_waste_streams(generator, self.waste_types)
        
        if not active_streams:
            return 0, {}

        potential_collections = {}
        remaining_capacity = target_volume
        
        for waste_type, stream in active_streams.items():
            if remaining_capacity <= 0:
                break
                
            collectible_amount = min(
                stream.volume,                     
                self.collection_capacity * self.efficiency,  
                remaining_capacity                   
            )
            
            if collectible_amount > 0:
                potential_collections[waste_type] = collectible_amount
                remaining_capacity -= collectible_amount

        if not potential_collections:
            return 0, {}

        allowed_collections, overflow = check_storage_capacity(
            {},  # We're checking just vehicle capacity
            potential_collections,
            target_volume
        )

        if overflow > 0:
            handle_storage_event(
                generator,
                overflow,
                generator.region
            )

        # Process the actual collections
        collected_waste = {}
        total_collected = 0
        
        for waste_type, amount in allowed_collections.items():
            if amount <= 0:
                continue
                
            stream = active_streams[waste_type]
            
            stream.volume -= amount
            generator.current_storage -= amount
            
            collected_waste[waste_type] = amount
            total_collected += amount
            
            SimulationState.get_instance().track_remove_waste(
                generator.region, waste_type, amount
            )

            SimulationState.get_instance().track_transport_flow(
                source_type="generator",
                source_name=generator.name,
                target_type="collector", 
                target_name=self.name,
                waste_type=waste_type,
                volume=amount,
                timestamp=self.env.now,
                transport_method="collection_vehicle"
            )
            
            self.collected_waste[waste_type] += amount
        
        return total_collected, collected_waste

    def _add_to_collection_center(self, collected_waste):
        """Add collected waste to collection center with overflow handling"""
        if not collected_waste:
            return
        
        current_total = sum(self.collection_center.current_storage.values())
        available_space = self.collection_center.waste_storage_capacity - current_total
        total_to_add = sum(collected_waste.values())
        
        if total_to_add <= available_space:
            for waste_type, amount in collected_waste.items():
                self.collection_center.current_storage[waste_type] += amount
        else:
            scaling_factor = available_space / total_to_add if total_to_add > 0 else 0
            overflow_amount = total_to_add - available_space
            
            for waste_type, amount in collected_waste.items():
                scaled_amount = amount * scaling_factor
                self.collection_center.current_storage[waste_type] += scaled_amount
                
            handle_storage_event(
                self,
                overflow_amount,
                self.region
            )

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
                raise ValueError(f"Error in transport management: {str(e)}")
            
            yield self.env.timeout(1.0)

    def update_efficiency(self):
        """Efficiency update"""
        current_time = self.env.now
        utilization = calculate_utilization(
            self.collection_center.current_storage, 
            self.collection_center.waste_storage_capacity
        )
        
        kanban_signals = len(self.kanban_manager.get_signals(self.env.now))
        
        self.efficiency = calculate_efficiency_multiplier(
            self.inventory_policy, self.stock_strategy, 
            utilization, kanban_signals, current_time
        )
        
        # Clamp efficiency
        self.efficiency = max(0.3, min(1.2, self.efficiency))

    def collection_loop(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            
            current_time = self.env.now

            self.update_efficiency()

            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                is_failed = self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)
                
                if is_failed and self.status == EntityStatus.FAILED:
                    self.efficiency = 0.5
                elif not is_failed and self.status == EntityStatus.OPERATIONAL:
                    if hasattr(self, '_was_failed') and self._was_failed:
                        base_recovery = 0.8
                        if self.inventory_policy == InventoryPolicy.PULL and self.stock_strategy == StockStrategy.ON_DEMAND:
                            self.efficiency = base_recovery * 1.1
                        else:
                            self.efficiency = base_recovery
                
                # Track previous failure state
                self._was_failed = (self.status == EntityStatus.FAILED)

            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.collection_frequency)  
                continue

            self.collection_capacity = max(10, self.collection_capacity * self.efficiency)
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            base_timeout = self.collection_frequency
            if self.inventory_policy == InventoryPolicy.PULL and self.kanban_manager.get_signals(self.env.now):
                timeout = base_timeout
            else:
                timeout = base_timeout + self.rng.uniform(1, 4)
            
            yield self.env.timeout(timeout)

            current_time = self.env.now
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)

            if self.status == EntityStatus.FAILED:
                continue

            if not self.should_collect():
                continue

            kanban_signals = self.kanban_manager.get_signals(self.env.now)
            if kanban_signals and self.inventory_policy == InventoryPolicy.PULL:
                self._process_kanban_signals(kanban_signals)
            else:
                # Regular collection based on policy
                collection_cost = self._unified_collection_strategy()
                if collection_cost > 0:
                    print(f"{self.env.now}: {self.name} collection cost: {collection_cost:.8f}")

    def _process_kanban_signals(self, signals):
        """Process signals with acknowledgment and cross-region support"""
        for signal in signals:
            try:
                waste_type_enum = WasteType[signal['waste_type']]
            except KeyError:
                continue
            
            source_type = signal.get('source_type', 'generator')  
            source_id = signal.get('source_id', signal.get('generator_id')) 
            
            matching_generators = []
            
            match source_type:
                case "generator":
                    # Specific generator signal - look for that exact generator
                    matching_generators = [
                        g for g in get_prioritized_generators(self)
                        if (g.name == source_id and 
                            waste_type_enum in g.waste_streams and 
                            g.waste_streams[waste_type_enum].volume > 0)
                    ]
                case "treatment":
                    # Treatment facility needs waste - find any generators with this waste type
                    # Prioritize based on volume and distance, not specific source
                    matching_generators = [
                        g for g in get_prioritized_generators(self)
                        if (waste_type_enum in g.waste_streams and 
                            g.waste_streams[waste_type_enum].volume > 0)
                    ]
                case _:
                    # Unknown source type - treat as general request
                    matching_generators = [
                        g for g in get_prioritized_generators(self)
                        if (waste_type_enum in g.waste_streams and 
                            g.waste_streams[waste_type_enum].volume > 0)
                    ]
            
            # Process the matching generators
            if matching_generators:
                for generator in matching_generators:
                    if self._find_available_vehicle():
                        self.collect_from_generator(generator)
                        
                        self.kanban_manager.acknowledge_signal(signal['id'])
                        break  # Only collect from one generator per signal
                    else:
                        break  # No point checking more generators if no vehicles available
            else:
                # Acknowledge the signal to prevent it from staying active forever
                self.kanban_manager.acknowledge_signal(signal['id'])

    def should_collect(self) -> bool:
        utilization = calculate_utilization(
            self.collection_center.current_storage,
            self.collection_center.waste_storage_capacity
        )
        
        if self.inventory_policy == InventoryPolicy.PUSH:
            base_threshold = get_adaptive_threshold(self.stock_strategy, self.env.now)
            push_threshold = min(0.80, base_threshold + 0.10)  # +10% buffer for PUSH
            should = utilization < push_threshold
            return should
            
        elif self.inventory_policy == InventoryPolicy.PULL:
            signals = self.kanban_manager.get_signals(self.env.now)
            if signals:
                return True
                
            # PULL uses much lower thresholds
            base_threshold = get_adaptive_threshold(self.stock_strategy, self.env.now)
            pull_threshold = max(0.15, base_threshold - 0.15)  # -15% for lean operation
            should = utilization < pull_threshold
            return should
        
        return False

    def transfer_waste_to_region(self, waste_type: WasteType, volume: float, destination: RegionType) -> bool:
        """Updated method using point-to-point transport"""
        if volume <= 0:
            return False
            
        if self.collection_center.current_storage[waste_type] < volume:
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
         
        success = self.transport_manager.request_transport(request)
        
        if success:
            # Remove from our storage immediately (it's now "in transit")
            self.collection_center.current_storage[waste_type] -= volume
            return True
        else:
            return False

    def collect_from_generator(self, generator):
        """Vehicle-based collection with proper overflow handling and storage management"""
        if self.status == EntityStatus.FAILED:
            return self.env.process(self._dummy_process(0))
        
        # Check if generator has any waste
        if generator.current_storage <= 0:
            return self.env.process(self._dummy_process(0))
        
        # Find available vehicle
        available_vehicle = self._find_available_vehicle()
        if not available_vehicle:
            return self.env.process(self._dummy_process(0))
            
        available_vehicle.in_transit = True

        # Calculate available space in collection center
        collection_center_available = (
            self.collection_center.waste_storage_capacity - 
            sum(self.collection_center.current_storage.values())
        )
        
        if collection_center_available <= 0:
            return self.env.process(self._dummy_process(0))
        
        # Calculate target collection volume considering all constraints
        target_volume = min(
            generator.current_storage,                    # What's available at generator
            self.collection_capacity * self.efficiency,  # Our collection capacity
            available_vehicle.capacity,                   # Vehicle capacity
            collection_center_available                   # Available storage space
        )
        
        if target_volume <= 0:
            return self.env.process(self._dummy_process(0))
        
        # Dispatch vehicle
        return self.env.process(self._dispatch_vehicle_for_collection(available_vehicle, generator, target_volume))

    def _dummy_process(self, return_value):
        """Helper for SimPy process returns"""
        yield self.env.timeout(0)
        return return_value

    def _unified_collection_strategy(self) -> float:
        """Strategy with 80/20 volume allocation between same/cross regions"""
        # Use volume-based regional prioritization
        volume_prioritized = get_prioritized_generators(self)
        
        total_cost = 0

        for generator in volume_prioritized:
            if generator.current_storage <= 0:
                continue
            
            # Check vehicle availability
            if not self._find_available_vehicle():
                break
            
            # Start collection (async process)
            self.collect_from_generator(generator)
            
            # Estimate cost based on distance
            _, distance = self._calculate_travel_time_to_generator(generator)
            estimated_cost = self.transport_cost + (distance * 0.5)
            total_cost += estimated_cost
        
        
        return total_cost
    
    def provide_waste_for_treatment(self, requested_amount: float, needed_types: set) -> Dict[WasteType, float]:
    
        provided_waste = {}
        remaining_request = requested_amount

        for waste_type in needed_types:
            if remaining_request <= 0:
                break
                
            available_in_storage = self.collection_center.current_storage[waste_type]
            if available_in_storage > 0:
                transfer_amount = min(available_in_storage, remaining_request)
                
                self.collection_center.current_storage[waste_type] -= transfer_amount
                provided_waste[waste_type] = provided_waste.get(waste_type, 0) + transfer_amount
                remaining_request -= transfer_amount

        return provided_waste
