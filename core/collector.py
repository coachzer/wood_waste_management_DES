import numpy as np
from models.enums import WasteType, RegionType, EntityStatus
from models.state import SimulationState
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES
from typing import Optional
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

from utils.capacity_utils import apply_capacity_constraints, handle_overflow_with_decision, check_storage_capacity

from core.kanban_manager import KanbanManager

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
        strategy="competitive",
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
        self.strategy = strategy
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

        # Initialize data collector (required for tracking)
        from monitoring.data_collector import DataCollector
        self.data_collector = DataCollector()

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

        print(f"{self.env.now}: Scheduled transport of {volume:.2f} m³ {waste_type} from {self.region} to {target_region.value}")

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

    def _check_failure_and_recovery(self, current_time) -> bool:
        """Check failure state and handle recovery"""
        if (self.status == EntityStatus.FAILED and 
            current_time >= self.recovery_time):
            print(f"{current_time}: Collector {self.name} has recovered from failure")
            self.status = EntityStatus.OPERATIONAL
            self.failure_time = None
            self.recovery_time = None
            self.availability = True
            return False
        return self.status == EntityStatus.FAILED

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
            self.data_collector.track_overflow(
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

                # Debug: Track collection activity
                # print(f"[COLLECTOR DEBUG] {self.name} collected {amount:.2f} m³ of {waste_type_enum}")
                # print(f"[COLLECTOR DEBUG] {self.name} total collected {waste_type_enum}: {self.collected_waste[waste_type_enum]:.2f}")

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

        # Pre-filter active waste streams and convert waste types
        active_streams = {}
        for waste_type_str, stream in generator.waste_streams.items():
            if stream.volume <= 0:
                continue
            
            # Normalize waste type string
            normalized_type = waste_type_str.replace(" ", "_").replace("-", "_")
            try:
                # First try direct enum lookup
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

        # Try to balance waste across collectors based on available storage
        available_collectors = [self] + [c for c in other_collectors if c.availability]
        if not available_collectors:
            return
            
        total_storage = sum(remaining_capacity.values())
        if total_storage <= 0:
            return

        total_cost = 0
        for waste_type, waste_stream in active_streams.items():
            # Calculate target volumes for each collector based on their capacity ratio
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
            self.data_collector.track_overflow(
                "collector",
                result.overflow_amount,
                strategy,
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
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'collector_failure'):
                self.check_failure(current_time, self.uncertainty_set.collector_failure.probability)

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
                # Default to competitive/collaborative collection
                prioritized_generators = get_prioritized_generators()
                collection_cost = 0
                
                # Get other collectors for collaboration
                state = SimulationState.get_instance()
                other_collectors = [
                    c for c in state.collectors 
                    if c != self and c.availability and c.region_type == self.region_type
                ]
                
                if self.strategy == "competitive":
                    collection_cost = handle_competitive_collection(
                        self, prioritized_generators
                    )
                elif self.strategy == "collaborative" and other_collectors:
                    collection_cost = handle_collaborative_collection(
                        self, prioritized_generators
                    )

                if collection_cost > 0:
                    print(
                        f"{self.env.now}: {self.name} collection operation cost: {collection_cost:.8f}"
                    )
