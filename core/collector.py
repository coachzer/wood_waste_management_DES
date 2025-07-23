import numpy as np
from typing import Dict, List
from models.enums import WasteType, RegionType, EntityStatus
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES, get_distance
from typing import Optional
from utils.capacity_utils import apply_capacity_constraints, handle_overflow_with_decision, check_storage_capacity
from core.kanban_manager import KanbanManager
from core.collector_utils import (
    collect_from_single_generator,
    get_available_vehicle,
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
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.waste_types = set(waste_types) if waste_types else set()
        self.kanban_manager = kanban_manager or KanbanManager()
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        # Store original region string for tracking
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

        # Initialize vehicle fleet
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

    def schedule_transport(
            self, 
            waste_type: WasteType, 
            volume: float, 
            target_region: RegionType
        ) -> bool:
        """Schedule waste transport to target region using actual distances"""
        # Check if we have waste to transport
        if self.collection_center.current_storage[waste_type] < volume:
            print(f"{self.env.now}: Insufficient {waste_type} for transport")
            return False

        # Get route and distance using the distance matrix
        route, total_distance = get_distance(self.region_type, target_region)

        print(f"{self.env.now}: Transporting {volume:.2f} m³ of {waste_type} from {self.region} to {target_region.value}")
        print(f"  Route: {route}, Total distance: {total_distance:.1f} km")

        if not route or total_distance == 0:
            print(f"{self.env.now}: No valid route from {self.region_type} to {target_region}")
            return False

        # Find available vehicle and verify capacity
        vehicle = get_available_vehicle(self.vehicles)
        if not vehicle or volume > vehicle.capacity:
            print(f"{self.env.now}: No suitable vehicles available for transport")
            return False

        average_speed_kmh = 50.0
        transport_time_hours = total_distance / average_speed_kmh
        transport_time_days = transport_time_hours / 24.0  # Convert to days for simulation time

        # Calculate transport cost based on distance
        cost_per_km = 2.0  # Cost per kilometer
        transport_cost = total_distance * cost_per_km * volume
        
        # Remove waste from collection center before updating vehicle
        self.collection_center.current_storage[waste_type] -= volume

        # Update vehicle status
        vehicle.current_load = volume
        vehicle.destination = target_region
        vehicle.estimated_arrival = self.env.now + transport_time_days
        vehicle.in_transit = True

        # Track waste removal from current region
        SimulationState.get_instance().track_waste_collection(
            self.region, waste_type, volume
        )

        # Add to active transports with distance and cost information
        self.active_transports.append(
            {
                "vehicle": vehicle,
                "waste_type": waste_type,
                "volume": volume,
                "arrival_time": vehicle.estimated_arrival,
                "route": route,
                "distance": total_distance,
                "transport_cost": transport_cost
            }
        )

        print(f"{self.env.now}: Scheduled transport of {volume:.2f} m³ {waste_type} from {self.region} to {target_region.value}")
        print(f"  Distance: {total_distance:.1f} km, Estimated travel time: {transport_time_hours:.1f} hours, Cost: ${transport_cost:.2f}")

        return True

    def manage_transport(self):
        """Process to manage ongoing transports"""
        while True:
            current_time = self.env.now

            try:
                # Check completed transports
                completed = check_completed_transports(self.active_transports, current_time)

                # Process completed transports and update collection centers
                for transport in completed:
                    handle_completed_transport(transport, current_time)
                    self.active_transports.remove(transport)

            except Exception as e:
                print(f"Error in transport management: {str(e)}")

            yield self.env.timeout(1.0)  # Check every hour

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
            return 0

        # Pre-filter active waste streams, only allow collector's waste_types
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0 and (waste_type in self.waste_types or (hasattr(waste_type, 'value') and waste_type.value in self.waste_types))
        }

        if not active_streams:
            return 0

        # Calculate potential collections - convert waste_type to enum and maintain mapping
        potential_collections = {}
        enum_to_original = {}  # Track mapping from enum to original string

        for waste_type_str, stream in active_streams.items():
            # Convert WasteType enum to string value if needed
            if isinstance(waste_type_str, WasteType):
                waste_type_value = waste_type_str.value
            else:
                waste_type_value = waste_type_str

            waste_type_enum = None

            # Map all WasteType enum values by .value
            mapping = {wt.value: wt for wt in WasteType}
            waste_type_enum = mapping.get(waste_type_value)
            if not waste_type_enum:
                print(f"Warning: Invalid waste type {waste_type_value}")
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
                self.env.now
            )

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

        if total_collected > 0:
            generator.mark_collected()
            return self.transport_cost + (0.1 * total_collected)
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

            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)

            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            # Add a small offset to avoid exact synchronization with generators
            offset = self.rng.uniform(1, 4)  # Random 1-4 day offset
            yield self.env.timeout(self.collection_frequency + offset)

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

            # Kanban signal processing for pull system
            kanban_signals = self.kanban_manager.get_signals()
            if kanban_signals:
                # Prioritize collection based on Kanban signals
                for signal in kanban_signals:
                    try:
                        # Convert waste_type string to enum
                        waste_type_enum = WasteType[signal['waste_type']]
                    except KeyError:
                        print(f"Warning: Invalid waste type in Kanban signal: {signal['waste_type']}")
                        continue
                    
                    # Find generators with matching waste type and region
                    prioritized_generators = [
                        g for g in get_prioritized_generators()
                        if waste_type_enum in g.waste_streams and g.region == self.region
                    ]
                    for generator in prioritized_generators:
                        self.collect_from_generator(generator)
                self.kanban_manager.clear_signals()
            else:
                prioritized_generators = get_prioritized_generators()
                collection_cost = self._unified_collection_strategy(prioritized_generators)

                if collection_cost > 0:
                    print(f"{self.env.now}: {self.name} collection operation cost: {collection_cost:.8f}")

    def collect_waste_for_demand(self, required_amount):
        """Collect waste based on treatment plant demand with storage-based adjustments"""

        state = SimulationState.get_instance()
        for gen in state.generators:
            if gen.region_type == self.region_type and hasattr(gen, "generate_on_demand"):
                gen.generate_on_demand()

        collected_amounts = dict.fromkeys(WasteType, 0.0)
        total_collected = 0
        state = SimulationState.get_instance()

        generators_storage = [
            (g, g.current_storage / g.waste_storage_capacity)
            for g in state.generators
            if g.region_type == self.region_type and g.current_storage > 0
        ]

        if generators_storage:
            avg_storage = sum(ratio for _, ratio in generators_storage) / len(
                generators_storage
            )
            if avg_storage < 0.3:
                required_amount *= self.rng.uniform(1.0, 1.2)
            elif avg_storage > 0.7:
                required_amount *= self.rng.uniform(0.6, 0.8)

        generators_storage.sort(key=lambda x: x[1], reverse=True)
        eligible_generators = [g for g, _ in generators_storage]

        for generator in eligible_generators:
            total_collected = collect_from_single_generator(
                self, generator, required_amount, total_collected, collected_amounts
            )
            if total_collected >= required_amount:
                break

        result = apply_capacity_constraints(
            sum(collected_amounts.values()),
            0,  # No additional amount to add
            self.collection_capacity * self.efficiency
        )

        if result.overflow_amount > 0:
            # Scale down collected amounts proportionally
            scaling_factor = result.allowed_amount / sum(collected_amounts.values())
            for waste_type in collected_amounts:
                collected_amounts[waste_type] *= scaling_factor

                
            _, strategy = handle_overflow_with_decision(
                self,
                result.overflow_amount,
                self.region
            )
            self.waste_monitor.track_overflow(
                "collector",
                result.overflow_amount,
                strategy,
                self.env.now
            )

        return collected_amounts

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
        """Provide waste to treatment plant from storage or by collecting"""
        provided_waste = {}
        remaining_request = requested_amount
        
        # First, check our storage
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
        
        # If still need more, collect from generators
        if remaining_request > 0:
            fresh_collected = self.collect_for_immediate_transfer(remaining_request, needed_types)
            for waste_type, amount in fresh_collected.items():
                provided_waste[waste_type] = provided_waste.get(waste_type, 0) + amount
        
        return provided_waste

    def collect_for_immediate_transfer(self, needed_amount: float, needed_types: set) -> Dict[WasteType, float]:
        """Collect waste immediately for transfer to treatment plant"""
        state = SimulationState.get_instance()
        collected = {}
        
        # Find generators in our region with needed waste types
        local_generators = [
            g for g in state.generators 
            if g.region_type == self.region_type and g.current_storage > 0
        ]
        
        remaining_needed = needed_amount
        
        for generator in local_generators:
            if remaining_needed <= 0:
                break
                
            for waste_type in needed_types:
                if remaining_needed <= 0:
                    break
                    
                if waste_type in generator.waste_streams:
                    available = generator.waste_streams[waste_type].volume
                    if available > 0:
                        collect_amount = min(available, remaining_needed)
                        
                        # Update generator
                        generator.waste_streams[waste_type].volume -= collect_amount
                        generator.current_storage -= collect_amount
                        
                        # Track collection
                        collected[waste_type] = collected.get(waste_type, 0) + collect_amount
                        remaining_needed -= collect_amount
                        
                        print(f"Collected {collect_amount:.2f} m³ of {waste_type} from {generator.name}")
        
        return collected

