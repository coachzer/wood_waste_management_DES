import numpy as np
from typing import Dict, List
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES, get_distance
from typing import Optional
from utils.capacity_utils import handle_overflow_with_decision, check_storage_capacity
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
        """Expose collection center's waste_storage_capacity for compatibility."""
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

        self.waste_monitor = waste_monitor
        if waste_monitor is None:
            raise ValueError("waste_monitor is required for TreatmentOperator")

        # Initialize RNG for collection adjustments
        self.rng = np.random.default_rng(42)  # For reproducibility

        # Start collection process
        self.process = env.process(self.collection_loop())
        self.transport_process = env.process(self.manage_transport())

    def _find_available_vehicle(self):
        """Find an available vehicle for collection"""
        for vehicle in self.vehicles:
            if not vehicle.in_transit:
                return vehicle
        return None

    def _calculate_travel_time_to_generator(self, generator):
        """Calculate travel time to generator (simplified)"""
        from models.distances import get_distance
        
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
        
        # Calculate travel time
        travel_time, distance = self._calculate_travel_time_to_generator(generator)
        
        print(f"[VEHICLE DISPATCH] {vehicle.id} dispatched to {generator.name} "
            f"({distance:.1f}km, {travel_time:.4f} days)")
        
        # Mark vehicle as busy
        vehicle.in_transit = True
        vehicle.destination = generator.region_type
        vehicle.estimated_arrival = current_time + travel_time
        
        # Travel to generator
        yield self.env.timeout(travel_time)
        
        # Perform collection at site
        collected_amount, collected_waste = self._perform_collection_at_site(generator, target_volume)
        
        if collected_amount > 0:
            print(f"[COLLECTION SUCCESS] {vehicle.id} collected {collected_amount:.1f} m³ from {generator.name}")
            
            # Update vehicle load
            vehicle.current_load = collected_amount
            
            # Travel back to collection center
            yield self.env.timeout(travel_time)
            
            # Add collected waste to collection center with overflow handling
            self._add_to_collection_center(collected_waste)
            
            print(f"[VEHICLE RETURN] {vehicle.id} returned and unloaded {collected_amount:.1f} m³")
            
            # Calculate collection cost
            collection_cost = self.transport_cost + (distance * 0.1 * collected_amount)
        else:
            print(f"[COLLECTION FAILED] {vehicle.id} collected nothing from {generator.name}")
            # Still need to travel back
            yield self.env.timeout(travel_time)
            collection_cost = self.transport_cost  # Base cost for attempt
        
        # Vehicle is now available again
        vehicle.in_transit = False
        vehicle.current_load = 0
        vehicle.destination = self.region_type  # Back home
        
        return collection_cost

    def _perform_collection_at_site(self, generator, target_volume):
        """Perform actual waste collection at generator site with proper constraint checking"""
        # Use existing utility to filter active waste streams
        active_streams = filter_active_waste_streams(generator, self.waste_types)
        
        if not active_streams:
            print(f"[NO COMPATIBLE WASTE] {generator.name} has no waste types we can collect")
            return 0, {}

        # Calculate potential collections for each waste type
        potential_collections = {}
        remaining_capacity = target_volume
        
        for waste_type, stream in active_streams.items():
            if remaining_capacity <= 0:
                break
                
            # Amount we could collect from this stream
            collectible_amount = min(
                stream.volume,                           # What's available
                self.collection_capacity * self.efficiency,  # Our capacity
                remaining_capacity                       # Remaining vehicle space
            )
            
            if collectible_amount > 0:
                potential_collections[waste_type] = collectible_amount
                remaining_capacity -= collectible_amount

        if not potential_collections:
            return 0, {}

        # Use existing capacity checking utility
        allowed_collections, overflow = check_storage_capacity(
            {},  # We're not checking existing storage, just vehicle capacity
            potential_collections,
            target_volume
        )

        # Handle any overflow at generator level
        if overflow > 0:
            print(f"[COLLECTION OVERFLOW] {overflow:.1f} m³ could not be collected due to capacity constraints")

        # Process the actual collections
        collected_waste = {}
        total_collected = 0
        
        for waste_type, amount in allowed_collections.items():
            if amount <= 0:
                continue
                
            # Find corresponding stream
            stream = active_streams[waste_type]
            
            # Update generator storage (remove collected waste)
            stream.volume -= amount
            generator.current_storage -= amount
            
            # Track what we collected
            collected_waste[waste_type] = amount
            total_collected += amount
            
            # Track collection in simulation state
            SimulationState.get_instance().track_waste_collection(
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
            
            print(f"[WASTE COLLECTED] {amount:.1f} m³ of {waste_type.value} from {generator.name}")
        
        return total_collected, collected_waste

    def _add_to_collection_center(self, collected_waste):
        """Add collected waste to collection center with overflow handling"""
        if not collected_waste:
            return
        
        # Check current available space
        current_total = sum(self.collection_center.current_storage.values())
        available_space = self.collection_center.waste_storage_capacity - current_total
        total_to_add = sum(collected_waste.values())
        
        if total_to_add <= available_space:
            # Everything fits - simple addition
            for waste_type, amount in collected_waste.items():
                self.collection_center.current_storage[waste_type] += amount
            print(f"[STORAGE SUCCESS] Added {total_to_add:.1f} m³ to collection center")
        else:
            # Need to handle overflow
            print(f"[STORAGE OVERFLOW] Trying to add {total_to_add:.1f} m³ but only {available_space:.1f} m³ available")
            
            # Use existing overflow handling
            scaling_factor = available_space / total_to_add if total_to_add > 0 else 0
            overflow_amount = total_to_add - available_space
            
            for waste_type, amount in collected_waste.items():
                scaled_amount = amount * scaling_factor
                self.collection_center.current_storage[waste_type] += scaled_amount
                
                # Track overflow for the portion that couldn't be stored
                lost_amount = amount - scaled_amount
                if lost_amount > 0:
                    print(f"[OVERFLOW] Lost {lost_amount:.1f} m³ of {waste_type.value}")
            
            # Use existing overflow tracking
            _, strategy = handle_overflow_with_decision(self, overflow_amount, self.region)
            self.waste_monitor.track_overflow(
                facility_type="collector",
                volume=overflow_amount,
                strategy=strategy,
                timestamp=self.env.now,
                region=self.region
            )

    def _get_distance_prioritized_generators(self, available_generators):
        """Get generators with 80% nearest / 20% next-nearest logic"""
        # Calculate distances
        generator_distances = []
        for generator in available_generators:
            if generator.current_storage > 0:
                # Use existing distance function
                if generator.region_type != self.region_type:
                    distance = get_distance(self.region_type, generator.region_type)
                else:
                    distance = 20.0  # Default same-region distance
                generator_distances.append((generator, distance))
        
        # Sort by distance
        generator_distances.sort(key=lambda x: x[1])
        
        if not generator_distances:
            return []
        
        # 80% nearest, 20% second nearest
        if len(generator_distances) == 1:
            return [generator_distances[0][0]]
        
        if self.rng.random() < 0.2 and len(generator_distances) > 1:
            print(f"[DISTANCE ROUTING] {self.name} choosing 2nd nearest generator")
            return [generator_distances[1][0], generator_distances[0][0]]  
        else:
            return [g[0] for g in generator_distances]

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

    def update_efficiency(self):
        """Efficiency update"""
        current_time = self.env.now
        utilization = calculate_utilization(
            self.collection_center.current_storage, 
            self.collection_center.waste_storage_capacity
        )
        
        kanban_signals = len(self.kanban_manager.get_signals())
        
        self.efficiency = calculate_efficiency_multiplier(
            self.inventory_policy, self.stock_strategy, 
            utilization, kanban_signals, current_time
        )
        
        # Clamp efficiency
        self.efficiency = max(0.3, min(1.2, self.efficiency))
        
        print(f"{current_time}: {self.name} ({self.inventory_policy.value}/{self.stock_strategy.value}) "
            f"efficiency: {self.efficiency:.3f}, utilization: {utilization:.2f}")
        
    def _handle_overflow(self, overflow_amount):
        """Handle overflow situation"""
        _, strategy = handle_overflow_with_decision(self, overflow_amount, self.region)
        self.waste_monitor.track_overflow(
            "collector", 
            overflow_amount, 
            strategy, 
            self.env.now, 
            self.region
        )

    def collection_loop(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            current_time = self.env.now
            print(f"{current_time}: Collector {self.name} starting collection process")

            self.update_efficiency()

            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                is_failed = self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)
                
                if is_failed and self.status == EntityStatus.FAILED:
                    self.efficiency = 0.5  # Reduce efficiency on failure
                elif not is_failed and self.status == EntityStatus.OPERATIONAL:
                    if hasattr(self, '_was_failed') and self._was_failed:
                        base_recovery = 0.8
                        if self.inventory_policy == InventoryPolicy.PULL and self.stock_strategy == StockStrategy.ON_DEMAND:
                            self.efficiency = base_recovery * 1.1
                        elif self.inventory_policy == InventoryPolicy.PUSH and self.stock_strategy == StockStrategy.FULL_STOCK:
                            self.efficiency = base_recovery * 0.9
                        else:
                            self.efficiency = base_recovery
                
                # Track previous failure state
                self._was_failed = (self.status == EntityStatus.FAILED)

            # Skip collection immediately if failed (before waiting)
            if self.status == EntityStatus.FAILED:
                print(f"{current_time}: Collector {self.name} is currently failed, skipping collection cycle")
                yield self.env.timeout(self.collection_frequency)  # Still wait before next check
                continue

            # Apply efficiency to capacity and costs
            self.collection_capacity = max(10, self.collection_capacity * self.efficiency)
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            base_timeout = self.collection_frequency
            if self.inventory_policy == InventoryPolicy.PULL and self.kanban_manager.get_signals():
                print(f"{current_time}: Collector {self.name} has kanban signals, using base frequency")
                timeout = base_timeout
            else:
                print(f"{current_time}: Collector {self.name} no kanban signals, adjusting frequency")
                timeout = base_timeout + self.rng.uniform(1, 4)
            
            yield self.env.timeout(timeout)

            # Check status again after timeout (entity might have failed/recovered during wait)
            current_time = self.env.now
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)

            if self.status == EntityStatus.FAILED:
                print(f"{current_time}: Collector {self.name} failed during timeout, skipping collection")
                continue

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
                prioritized_generators = get_prioritized_generators(self)
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
                g for g in get_prioritized_generators(self)
                if waste_type_enum in g.waste_streams and g.region == self.region
            ]
            
            for generator in prioritized_generators:
                self.collect_from_generator(generator)

    def should_collect(self) -> bool:
        utilization = calculate_utilization(
            self.collection_center.current_storage,
            self.collection_center.waste_storage_capacity
        )
        
        if self.inventory_policy == InventoryPolicy.PUSH:
            # PUSH: Higher inventory targets 
            base_threshold = get_adaptive_threshold(self.stock_strategy, self.env.now)
            push_threshold = min(0.80, base_threshold + 0.10)  # +10% buffer for PUSH
            should = utilization < push_threshold
            if should:
                print(f"[PUSH COLLECT] {self.name}: {utilization:.2f} < {push_threshold:.2f}")
            return should
            
        elif self.inventory_policy == InventoryPolicy.PULL:
            # PULL: Kanban-first, then lean thresholds (20-40% full)
            signals = self.kanban_manager.get_signals()
            if signals:
                print(f"[PULL COLLECT] {self.name}: {len(signals)} kanban signals")
                return True
                
            # PULL uses much lower thresholds
            base_threshold = get_adaptive_threshold(self.stock_strategy, self.env.now)
            pull_threshold = max(0.15, base_threshold - 0.15)  # -15% for lean operation
            should = utilization < pull_threshold
            if should:
                print(f"[PULL COLLECT] {self.name}: {utilization:.2f} < {pull_threshold:.2f}")
            return should
        
        return False

    def transfer_waste_to_region(self, waste_type: WasteType, volume: float, destination: RegionType) -> bool:
        """Updated method using point-to-point transport"""
        if volume <= 0:
            print(f"{self.env.now}: {self.name} attempted to transfer zero or negative volume of {waste_type.value}")
            return False
            
        # Check if we have enough waste in storage
        if self.collection_center.current_storage[waste_type] < volume:
            print(f"{self.env.now}: {self.name} insufficient waste in storage for transport request")
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
        print(f"{self.env.now}: {self.name} requesting transport of {volume:.2f} m³ {waste_type.value} to {destination.value}")
        success = self.transport_manager.request_transport(request)
        
        if success:
            # Remove from our storage immediately (it's now "in transit")
            self.collection_center.current_storage[waste_type] -= volume
            print(f"{self.env.now}: {self.name} scheduled transport of {volume:.2f} m³ {waste_type.value}")
            return True
        else:
            print(f"{self.env.now}: {self.name} transport request failed")
            return False

    def collect_from_generator(self, generator):
        """Vehicle-based collection with proper overflow handling and storage management"""
        if not self.availability:
            return self.env.process(self._dummy_process(0))
        
        # Check if generator has any waste
        if generator.current_storage <= 0:
            return self.env.process(self._dummy_process(0))
        
        # Find available vehicle
        available_vehicle = self._find_available_vehicle()
        if not available_vehicle:
            print(f"[NO VEHICLES] {self.name} has no available vehicles for collection from {generator.name}")
            return self.env.process(self._dummy_process(0))
        
        # Calculate available space in collection center
        collection_center_available = (
            self.collection_center.waste_storage_capacity - 
            sum(self.collection_center.current_storage.values())
        )
        
        if collection_center_available <= 0:
            print(f"[STORAGE FULL] {self.name} collection center is full, cannot collect from {generator.name}")
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
        
        print(f"[COLLECTION PLANNED] {self.name} planning to collect {target_volume:.1f} m³ from {generator.name}")
        
        # Dispatch vehicle
        return self.env.process(self._dispatch_vehicle_for_collection(available_vehicle, generator, target_volume))


    def _dummy_process(self, return_value):
        """Helper for SimPy process returns"""
        yield self.env.timeout(0)
        return return_value

    def _unified_collection_strategy(self, prioritized_generators: List) -> float:
        """Strategy with 80/20 volume allocation between same/cross regions"""
        # Use volume-based regional prioritization
        volume_prioritized = get_prioritized_generators(self)
        
        total_cost = 0
        collected_same_region = 0
        collected_cross_region = 0
        
        for generator in volume_prioritized:
            if generator.current_storage <= 0:
                continue
            
            # Check vehicle availability
            if not self._find_available_vehicle():
                print(f"[VEHICLE LIMIT] {self.name} no more vehicles available")
                break
            
            # Start collection (async process)
            self.collect_from_generator(generator)
            
            # Track volume allocation for reporting
            estimated_collection = min(
                generator.current_storage,
                self.collection_capacity * self.efficiency
            )
            
            if generator.region_type == self.region_type:
                collected_same_region += estimated_collection
            else:
                collected_cross_region += estimated_collection
            
            # Estimate cost based on distance
            _, distance = self._calculate_travel_time_to_generator(generator)
            estimated_cost = self.transport_cost + (distance * 0.5)
            total_cost += estimated_cost
            
            print(f"[VOLUME COLLECTION] {self.name} dispatching to {generator.name} "
                f"({generator.region_type.value}, {estimated_collection:.1f}m³, €{estimated_cost:.2f})")
        
        # Report final volume allocation
        total_collected = collected_same_region + collected_cross_region
        if total_collected > 0:
            same_pct = (collected_same_region / total_collected) * 100
            cross_pct = (collected_cross_region / total_collected) * 100
            print(f"[VOLUME SUMMARY] {self.name}: {same_pct:.1f}% same region ({collected_same_region:.1f}m³), "
                f"{cross_pct:.1f}% cross region ({collected_cross_region:.1f}m³)")
        
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
                
                # print(f"Transferred {transfer_amount:.2f} m³ of {waste_type} from storage")
        
        # If we can't fulfill the request, that's okay - treatment will have to wait
        # total_provided = sum(provided_waste.values())
        # if total_provided < requested_amount:
            # shortfall = requested_amount - total_provided
            # print(f"Collector {self.name} storage insufficient: requested {requested_amount:.2f} m³, "
            # #     f"provided {total_provided:.2f} m³, shortfall {shortfall:.2f} m³")

        return provided_waste