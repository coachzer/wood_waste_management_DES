from models.enums import WasteType, RegionType, EntityStatus
from models.state import SimulationState
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES
import numpy as np
from typing import Optional
from optimization.uncertainty import UncertaintySet
from core.collector_utils import (
    calculate_transport_route,
    get_available_vehicle,
    handle_completed_transport,
    check_completed_transports,
    handle_transport_delays,
    handle_collector_capacity,
    collect_from_single_generator,
    get_prioritized_generators,
    handle_competitive_collection,
    handle_collaborative_collection,
)

from utils.capacity_utils import apply_capacity_constraints, handle_overflow_generic, check_storage_capacity

class CollectorCompany(OperationalEntity):
    """A company that collects waste from generators"""

    def __init__(
        self,
        env,
        name,
        collection_capacity,
        collection_frequency,
        transport_cost,
        environmental_impact,
        efficiency,
        availability=True,
        strategy="competitive",
        region=None,
        num_vehicles: int = 3,
        vehicle_capacity: Optional[float] = None,
        uncertainty_set: Optional[UncertaintySet] = None,
    ):
        super().__init__()
        self.env = env
        self.name = name
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        self.strategy = strategy
        # Store original region string for tracking
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None
        self.uncertainty_set = uncertainty_set

        # Initialize collection center
        self.collection_center = CollectionCenter(
            region=self.region_type,  # Use enum for internal operations
            storage_capacity=collection_capacity * 2,  # Double the collection capacity
            current_storage={waste_type: 0.0 for waste_type in WasteType},
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
        self.collected_waste = {waste_type: 0.0 for waste_type in WasteType}

        # Initialize RNG for collection adjustments
        self.rng = np.random.default_rng(42)  # For reproducibility

        # Start collection process
        self.process = env.process(self.collect_waste())
        self.transport_process = env.process(self.manage_transport())

    def schedule_transport(
        self, waste_type: WasteType, volume: float, target_region: RegionType
    ) -> bool:
        """Schedule waste transport to target region"""
        # Check if we have waste to transport
        if self.collection_center.current_storage[waste_type] < volume:
            print(f"{self.env.now}: Insufficient {waste_type} for transport")
            return False

        # Get route and distance
        route, total_distance = calculate_transport_route(self.region_type, target_region)
        if not route:
            return False

        # Find available vehicle and verify capacity
        vehicle = get_available_vehicle(self.vehicles)
        if not vehicle or volume > vehicle.capacity:
            print(f"{self.env.now}: No suitable vehicles available for transport")
            return False

        # Calculate transport time (assume 60 km/h average speed)
        transport_time = total_distance / 60.0

        # Remove waste from collection center before updating vehicle
        self.collection_center.current_storage[waste_type] -= volume

        # First update the vehicle status
        vehicle.current_load = volume
        vehicle.destination = target_region
        vehicle.estimated_arrival = self.env.now + transport_time
        # Mark as in_transit last to ensure atomic operation
        vehicle.in_transit = True

        # Track waste removal from current region
        SimulationState.get_instance().track_waste_collection(
            self.region, waste_type, volume
        )

        # Add to active transports
        self.active_transports.append(
            {
                "vehicle": vehicle,
                "waste_type": waste_type,
                "volume": volume,
                "arrival_time": vehicle.estimated_arrival,
                "route": route
            }
        )

        print(f"{self.env.now}: Scheduled transport of {volume:.2f} m³ {waste_type.value} from {self.region} to {target_region.value}")

        return True

    def manage_transport(self):
        """Process to manage ongoing transports"""
        while True:
            current_time = self.env.now

            try:
                # Check completed transports
                completed = check_completed_transports(self.active_transports, current_time)
                
                # Handle potential vehicle delays
                handle_transport_delays(self.active_transports, current_time, self.rng)

                # Process completed transports and update collection centers
                for transport in completed:
                    handle_completed_transport(transport, current_time)
                    self.active_transports.remove(transport)

            except Exception as e:
                print(f"Error in transport management: {str(e)}")

            yield self.env.timeout(1.0)  # Check every hour

    def collect_from_generator(self, generator):
        """Collect waste from a generator, handling multiple waste types"""
        

        # Pre-filter active waste streams
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0
        }

        if not active_streams:
            return 0

        # Calculate potential collections
        potential_collections = {
            waste_type: min(
                stream.volume,
                self.collection_capacity * self.efficiency
            )
            for waste_type, stream in active_streams.items()
        }

        # Check storage capacity constraints
        allowed_collections, overflow_amount = check_storage_capacity(
            self.collection_center.current_storage,
            potential_collections,
            self.collection_center.storage_capacity
        )

        if overflow_amount > 0:
            handle_overflow_generic(
                self.data_collector,
                "collector",
                overflow_amount,
                "landfill",
                self.env.now
            )

        # Process allowed collections
        total_collected = 0.0
        for waste_type, amount in allowed_collections.items():
            if amount > 0:
                # Update generator's waste stream
                active_streams[waste_type].volume -= amount
                generator.current_storage -= amount

                # Track waste removal from generator's region
                SimulationState.get_instance().track_waste_collection(
                    generator.region, waste_type, amount
                )

                # Update collection center storage and tracking
                self.collection_center.current_storage[waste_type] += amount
                self.collected_waste[waste_type] += amount

                # Track waste addition to collector's region
                SimulationState.get_instance().track_waste_generation(
                    self.region, waste_type, amount
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
                collector.collection_center.storage_capacity
                - sum(collector.collection_center.current_storage.values()),
            )
            for collector in [self] + other_collectors
        }

        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0
        }

        # Try to balance waste across collectors based on available storage
        available_collectors = [self] + [c for c in other_collectors if c.availability]
        total_storage = sum(remaining_capacity.values())

        for waste_type, waste_stream in active_streams.items():
            # Calculate target volumes for each collector based on their capacity ratio
            for collector in available_collectors:
                capacity_ratio = remaining_capacity[collector.name] / total_storage
                target_volume = waste_stream.volume * capacity_ratio
                handle_collector_capacity(self,
                    collector, waste_type, target_volume, waste_stream, 
                    remaining_capacity, generator
                )

    def collect_waste_for_demand(self, required_amount):
        """Collect waste based on treatment plant demand with storage-based adjustments"""
        collected_amounts = {waste_type: 0.0 for waste_type in WasteType}
        total_collected = 0
        state = SimulationState.get_instance()

        generators_storage = [
            (g, g.current_storage / g.storage_capacity)
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

            handle_overflow_generic(
                self.data_collector,
                "collector",
                result.overflow_amount,
                "landfill",
                self.env.now
            )

        return collected_amounts

    def get_collection_summary(self):
        """Get summary of all collected waste by type"""
        capacity_with_efficiency = self.collection_capacity * self.efficiency
        return {
            waste_type: {
                "total_collected": amount,
                "collection_capacity_utilization": amount / capacity_with_efficiency,
            }
            for waste_type, amount in self.collected_waste.items()
            if amount > 0
        }

    def collect_waste(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            current_time = self.env.now
            
            # Check for failures if uncertainty set is available
            if self.uncertainty_set:
                self.check_failure(current_time, self.uncertainty_set.equipment_failure_rate)
            
            # Update collection parameters based on optimization
            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            # Add a small offset to avoid exact synchronization with generators
            offset = self.rng.uniform(1, 4)  # Random 1-4 hour offset
            yield self.env.timeout(self.collection_frequency + offset)

            # Skip collection if failed or unavailable
            if self.status == EntityStatus.FAILED:
                print(f"{current_time}: Collector {self.name} is currently failed, skipping collection")
                continue
            elif not self.availability:
                continue
            
            # Check for recovery
            if (self.status == EntityStatus.FAILED and 
                current_time >= self.recovery_time):
                print(f"{current_time}: Collector {self.name} has recovered from failure")
                self.status = EntityStatus.OPERATIONAL
                self.failure_time = None
                self.recovery_time = None

            prioritized_generators = get_prioritized_generators()

            collection_cost = 0
            if self.strategy == "competitive":
                collection_cost = handle_competitive_collection(
                    self, prioritized_generators
                )
            elif self.strategy == "collaborative":
                collection_cost = handle_collaborative_collection(
                    self, prioritized_generators
                )

            if collection_cost > 0:
                print(
                    f"{self.env.now}: {self.name} collection operation cost: {collection_cost:.8f}"
                )
