from models.enums import WasteType, RegionType
from models.state import SimulationState
from models.data_classes import Vehicle, CollectionCenter
from models.distances import REGION_COORDINATES, get_distance
import numpy as np
from typing import List, Optional, Tuple
from core.overflow import OverflowTracker


class CollectorCompany:
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
    ):
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
        # Convert region string to RegionType for internal use
        self.region_type = RegionType[region.upper()] if region else None

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

        # Initialize overflow tracker
        self.overflow_tracker = OverflowTracker()

        # Track active transports
        self.active_transports = []

        # Initialize waste tracking
        self.collected_waste = {waste_type: 0.0 for waste_type in WasteType}

        # Initialize RNG for collection adjustments
        self.rng = np.random.default_rng(42)  # For reproducibility

        # Start collection process
        self.process = env.process(self.collect_waste())
        self.transport_process = env.process(self.manage_transport())

    def calculate_transport_route(
        self, target_region: RegionType
    ) -> Tuple[List[RegionType], float]:
        """Calculate shortest path to target region and total distance"""
        if self.region_type == target_region:
            return [], 0.0

        distance = get_distance(self.region_type, target_region)
        return [target_region], distance

    def get_available_vehicle(self) -> Optional[Vehicle]:
        """Get first available vehicle"""
        return next(
            (v for v in self.vehicles if not v.in_transit and v.current_load == 0), None
        )

    def schedule_transport(
        self, waste_type: WasteType, volume: float, target_region: RegionType
    ) -> bool:
        """Schedule waste transport to target region"""
        # Check if we have waste to transport
        if self.collection_center.current_storage[waste_type] < volume:
            print(f"{self.env.now}: Insufficient {waste_type} for transport")
            return False

        # Get route and distance
        route, total_distance = self.calculate_transport_route(target_region)
        if not route:
            return False

        # Find available vehicle
        vehicle = self.get_available_vehicle()
        if not vehicle:
            print(f"{self.env.now}: No vehicles available for transport")
            return False

        # Calculate transport time (assume 60 km/h average speed)
        transport_time = total_distance / 60.0

        # Update vehicle status
        vehicle.in_transit = True
        vehicle.current_load = volume
        vehicle.destination = target_region
        vehicle.estimated_arrival = self.env.now + transport_time

        # Track waste removal from current region before moving
        SimulationState.get_instance().track_waste_collection(
            self.region, waste_type, volume
        )

        # Remove waste from collection center
        self.collection_center.current_storage[waste_type] -= volume

        # Add to active transports
        self.active_transports.append(
            {
                "vehicle": vehicle,
                "waste_type": waste_type,
                "volume": volume,
                "arrival_time": vehicle.estimated_arrival,
            }
        )

        print(
            f"{self.env.now}: Scheduled transport of {volume:.2f} m³ {waste_type} "
            f"to {target_region.value}, ETA: {transport_time:.2f} hours"
        )
        return True

    def manage_transport(self):
        """Process to manage ongoing transports"""
        while True:
            current_time = self.env.now

            # Check completed transports
            completed = []
            for transport in self.active_transports:
                if current_time >= transport["arrival_time"]:
                    vehicle = transport["vehicle"]
                    # Update vehicle status
                    vehicle.in_transit = False
                    vehicle.current_load = 0
                    vehicle.current_region = vehicle.destination
                    vehicle.destination = None
                    vehicle.estimated_arrival = None
                    completed.append(transport)
                    print(
                        f"{current_time}: Transport completed - Vehicle {vehicle.id} "
                        f"arrived at {vehicle.current_region.value}"
                    )

            try:
                # Handle vehicle breakdowns or delays
                for transport in self.active_transports:
                    if (
                        not transport["vehicle"].in_transit
                        or current_time < transport["arrival_time"]
                    ):
                        continue

                    # Simulate potential transport issues
                    if self.rng.random() < 0.05:  # 5% chance of delay
                        delay_hours = self.rng.uniform(1, 4)
                        transport["arrival_time"] += delay_hours
                        print(
                            f"{current_time}: Transport delayed - Vehicle {transport['vehicle'].id} "
                            f"new ETA: +{delay_hours:.1f} hours"
                        )

                # Remove completed transports and update collection centers
                for transport in completed:
                    # Update target collection center
                    target_collector = next(
                        (
                            c
                            for c in SimulationState.get_instance().collectors
                            if c.region_type == transport["vehicle"].current_region
                        ),
                        None,
                    )
                    if target_collector:
                        # Track waste addition to destination region
                        SimulationState.get_instance().track_waste_generation(
                            target_collector.region,
                            transport["waste_type"],
                            transport["volume"],
                        )
                        target_collector.collection_center.current_storage[
                            transport["waste_type"]
                        ] += transport["volume"]
                        print(
                            f"{current_time}: Added {transport['volume']:.2f} m³ to "
                            f"{target_collector.name}'s collection center"
                        )
                    self.active_transports.remove(transport)

            except Exception as e:
                print(f"Error in transport management: {str(e)}")

            yield self.env.timeout(1.0)  # Check every hour

    def collect_from_generator(self, generator):
        """Collect waste from a generator, handling multiple waste types"""
        total_collected = 0
        # Consider both vehicle capacity and collection center remaining capacity
        remaining_capacity = min(
            self.collection_capacity * self.efficiency,
            self.collection_center.storage_capacity
            - sum(self.collection_center.current_storage.values()),
        )

        # Pre-filter active waste streams
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0
        }

        for waste_type, waste_stream in active_streams.items():
            collectable_amount = min(waste_stream.volume, remaining_capacity)

            if collectable_amount > 0:
                # Update generator's waste stream
                waste_stream.volume -= collectable_amount
                generator.current_storage -= collectable_amount

                # Track waste removal from generator's region
                SimulationState.get_instance().track_waste_collection(
                    generator.region, waste_type, collectable_amount
                )

                # Update collection center storage
                self.collection_center.current_storage[waste_type] += collectable_amount
                # Update tracking
                self.collected_waste[waste_type] += collectable_amount

                # Track waste addition to collector's region
                SimulationState.get_instance().track_waste_generation(
                    self.region, waste_type, collectable_amount
                )

                remaining_capacity -= collectable_amount
                total_collected += collectable_amount

                print(
                    f"{self.env.now}: {self.name} collected {collectable_amount:.2f} m³ of {waste_type.value} from {generator.name}"
                )

        if total_collected > 0:
            generator.mark_collected()
            return self.transport_cost + (0.1 * total_collected)
        return 0

    def _process_collection(
        self,
        collector,
        waste_type,
        waste_stream,
        remaining_volume,
        remaining_capacity,
        generator,
        is_collaborative=False,
    ):
        """Helper method to process waste collection for a collector"""
        if remaining_volume <= 0 or remaining_capacity[collector.name] <= 0:
            return remaining_volume

        collectable_amount = min(remaining_volume, remaining_capacity[collector.name])

        if collectable_amount > 0:
            # Update generator
            waste_stream.volume -= collectable_amount
            generator.current_storage -= collectable_amount

            # Track waste removal from generator's region
            SimulationState.get_instance().track_waste_collection(
                generator.region, waste_type, collectable_amount
            )

            # Update collector
            collector.collected_waste[waste_type] += collectable_amount
            remaining_capacity[collector.name] -= collectable_amount

            # Track waste addition to collector's region
            SimulationState.get_instance().track_waste_generation(
                collector.region, waste_type, collectable_amount
            )

            collection_type = (
                "collaboratively collected"
                if is_collaborative
                else "collected remaining"
            )
            print(
                f"{self.env.now}: {collector.name} {collection_type} {collectable_amount:.2f} m³ of {waste_type.value}"
            )

        return remaining_volume - collectable_amount

    def transfer_waste_to_region(
        self, waste_type: WasteType, volume: float, target_region: RegionType
    ) -> bool:
        """Transfer waste from this collector to another region"""
        state = SimulationState.get_instance()
        target_collectors = [
            c
            for c in state.collectors
            if c.region_type == target_region and c.availability
        ]

        if not target_collectors:
            print(
                f"{self.env.now}: No available collectors in target region {target_region.value}"
            )
            return False

        # Schedule the transport
        if self.schedule_transport(waste_type, volume, target_region):
            print(f"{self.env.now}: Waste transfer initiated to {target_region.value}")
            return True
        return False

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
            remaining_volume = waste_stream.volume

            # Calculate target volumes for each collector based on their capacity ratio
            for collector in available_collectors:
                capacity_ratio = remaining_capacity[collector.name] / total_storage
                target_volume = waste_stream.volume * capacity_ratio
                # Check if collector is from a different region
                if collector.region_type != self.region_type:
                    # If different region, schedule transport
                    if target_volume > 0:
                        success = self.transfer_waste_to_region(
                            waste_type, target_volume, collector.region_type
                        )
                        if success:
                            # Track waste removal from current region
                            SimulationState.get_instance().track_waste_collection(
                                self.region, waste_type, target_volume
                            )
                else:
                    # Same region, use normal collection process
                    self._process_collection(
                        collector,
                        waste_type,
                        waste_stream,
                        target_volume,
                        remaining_capacity,
                        generator,
                        True,
                    )

    def _collect_from_single_generator(
        self, generator, required_amount, total_collected, collected_amounts
    ):
        """Collect waste from a single generator based on demand"""
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0 and total_collected < required_amount
        }

        for waste_type, stream in active_streams.items():
            collectable_amount = min(
                stream.volume,
                required_amount - total_collected,
                self.collection_capacity * self.efficiency,
            )

            if collectable_amount > 0:
                stream.volume -= collectable_amount
                generator.current_storage -= collectable_amount

                # Track waste removal from generator's region
                SimulationState.get_instance().track_waste_collection(
                    generator.region, waste_type, collectable_amount
                )

                # Track waste addition to collector's region
                SimulationState.get_instance().track_waste_generation(
                    self.region, waste_type, collectable_amount
                )

                # Update collection center storage
                self.collection_center.current_storage[waste_type] += collectable_amount
                collected_amounts[waste_type] += collectable_amount
                total_collected += collectable_amount

                print(
                    f"{self.env.now}: {self.name} collected {collectable_amount:.2f} m³ of {waste_type.value} from {generator.name}"
                )

                # Immediately remove from collector storage since it's going to treatment
                self.collection_center.current_storage[waste_type] -= collectable_amount

        return total_collected

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

        print(f"Eligible generators: {[g.name for g in eligible_generators]}")

        for generator in eligible_generators:
            total_collected = self._collect_from_single_generator(
                generator, required_amount, total_collected, collected_amounts
            )
            if total_collected >= required_amount:
                print(f"{self.name} collected enough waste for demand")
                break

        # Check for overflow (if the collector can't store all waste collected)
        if sum(collected_amounts.values()) > self.collection_capacity * self.efficiency:
            overflow_volume = (
                sum(collected_amounts.values())
                - self.collection_capacity * self.efficiency
            )

            # Determine severity level
            if self.collection_capacity * self.efficiency > 0.90:
                severity = "emergency"
            elif self.collection_capacity * self.efficiency > 0.85:
                severity = "critical"
            else:
                severity = "warning"

            # Landfill the excess waste and track it
            print(
                f"{self.env.now}: Landfilling {overflow_volume:.2f} m³ of waste from {self.name}"
            )
            self.overflow_tracker.track_overflow(
                facility_type="collector", volume=overflow_volume
            )

            # Calculate and apply penalty
            penalty = self.overflow_tracker.calculate_penalty(
                facility_type="collector", severity=severity, volume=overflow_volume
            )
            print(f"Overflow penalty applied to {self.name}: {penalty:.2f}")

            # Reduce collected waste
            reduction_factor = (self.collection_capacity * self.efficiency) / sum(
                collected_amounts.values()
            )
            for waste_type in collected_amounts:
                collected_amounts[waste_type] *= reduction_factor

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

    def _get_prioritized_generators(self):
        """Get generators sorted by priority and filtered by region"""
        state = SimulationState.get_instance()
        regional_generators = [
            g
            for g in state.generators
            if g.current_storage > 0 and g.region_type == self.region_type
        ]

        if not regional_generators:
            regional_generators = [g for g in state.generators if g.current_storage > 0]

        regional_generators.sort(key=lambda x: x.priority_level, reverse=True)
        return regional_generators

    def _handle_competitive_collection(self, prioritized_generators):
        """Handle competitive collection strategy"""
        if prioritized_generators and self.availability:
            return self.collect_from_generator(prioritized_generators[0])
        return 0

    def _handle_collaborative_collection(self, prioritized_generators):
        """Handle collaborative collection strategy"""
        if not self.availability:
            return

        state = SimulationState.get_instance()
        other_collectors = [
            c
            for c in state.collectors
            if c != self and c.availability and c.region_type == self.region_type
        ]

        total_collection_cost = 0
        for generator in prioritized_generators:
            if generator.current_storage <= 0:
                continue
            self.collect_with_collaboration(generator, other_collectors)
            total_collection_cost += self.transport_cost
        return total_collection_cost

    def collect_waste(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            # Update collection parameters based on optimization
            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            yield self.env.timeout(self.collection_frequency)

            if not self.availability:
                continue

            prioritized_generators = self._get_prioritized_generators()

            collection_cost = 0
            if self.strategy == "competitive":
                collection_cost = self._handle_competitive_collection(
                    prioritized_generators
                )
            elif self.strategy == "collaborative":
                collection_cost = self._handle_collaborative_collection(
                    prioritized_generators
                )

            if collection_cost > 0:
                print(
                    f"{self.env.now}: {self.name} collection operation cost: {collection_cost:.2f}"
                )
