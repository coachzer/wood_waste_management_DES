import numpy as np
from typing import Dict, List, Optional
from config.constants import (
    TRANSPORT_EMISSIONS_PER_M3_KM,
    FAILED_ENTITY_EFFICIENCY,
    TRAVEL_SPEED_KMH,
    LOCAL_COLLECTION_RATIO,
)
from core.transport_manager import PointToPointTransport, TransportPriority, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES, get_distance, get_closest_regions
from utils.capacity_utils import handle_storage_event, check_storage_capacity
from core.kanban_manager import KanbanManager

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
        transport_manager: PointToPointTransport = None,
        failure_config = None,
        seed = None
    ):
        self.uncertainty_set = uncertainty_set

        if failure_config is None and uncertainty_set:
            failure_config = uncertainty_set.collector_failure
        super().__init__(failure_config=failure_config, seed=seed)
        self.env = env
        self.name = name
        self.facility_type = "collector"
        self.expansion_count = 0    
        self.waste_types = set(waste_types) if waste_types else set()
        self.kanban_manager = kanban_manager or KanbanManager()
        self.inventory_policy = inventory_policy
        self.stock_strategy = stock_strategy
        self.transport_manager = transport_manager or PointToPointTransport()
        self.initial_collection_capacity = collection_capacity
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.initial_transport_cost = transport_cost
        self.transport_cost = transport_cost
        self.last_collection_cost = 0.0
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None

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
            raise ValueError("waste_monitor is required for CollectorCompany")

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

        travel_time_hours = distance / TRAVEL_SPEED_KMH
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
            self.last_collection_cost = collection_cost

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
        active_streams = self._filter_active_waste_streams(generator)

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
                completed = self._check_completed_transports(current_time)

                for transport in completed:
                    self._handle_completed_transport(transport)
                    self.active_transports.remove(transport)

            except Exception as e:
                raise ValueError(f"Error in transport management: {str(e)}")

            yield self.env.timeout(1.0)

    def update_efficiency(self):
        """Efficiency update"""
        current_time = self.env.now
        utilization = self._calculate_utilization()

        kanban_signals = len(self.kanban_manager.get_signals(self.env.now))

        self.efficiency = self._calculate_efficiency_multiplier(
            utilization, kanban_signals, current_time
        )

        # Clamp efficiency
        self.efficiency = max(0.3, min(1.2, self.efficiency))

    def collection_loop(self):
        """Periodically collect waste from generators based on strategy"""
        while True:

            current_time = self.env.now

            self.update_efficiency()

            if self.failure_config:
                self.check_failure(current_time, self.failure_config.probability)

            if self.status == EntityStatus.FAILED:
                self.efficiency = FAILED_ENTITY_EFFICIENCY
            elif self.status == EntityStatus.RECOVERING:
                self.efficiency = self.get_operational_efficiency()
            if self.status == EntityStatus.FAILED:
                yield self.env.timeout(self.collection_frequency)  
                continue

            self.collection_capacity = max(10, self.initial_collection_capacity * self.efficiency)
            self.transport_cost = min(100, self.initial_transport_cost * (2 - self.efficiency))

            base_timeout = self.collection_frequency
            if self.inventory_policy == InventoryPolicy.PULL and self.kanban_manager.get_signals(self.env.now):
                timeout = base_timeout
            else:
                timeout = base_timeout + self.rng.uniform(1, 4)

            yield self.env.timeout(timeout)

            if not self.should_collect():
                continue

            kanban_signals = [
                s for s in self.kanban_manager.get_signals(self.env.now)
                if s.get('source_type') != "market"
            ]
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
            # Market signals (source_type="market") are downstream demand for
            # treatment production (ADR 0002, Phase E), not upstream waste-
            # collection requests. Collectors must not consume or acknowledge
            # them -- doing so starves the treatment operator's event-driven
            # production loop, which is the sole consumer of these signals.
            if signal.get('source_type') == "market":
                continue

            waste_type_enum = signal['waste_type']

            source_type = signal.get('source_type', 'generator')  
            source_id = signal.get('source_id', signal.get('generator_id')) 
            current_time = self.env.now

            matching_generators = []

            match source_type:
                case "generator":
                    matching_generators = [
                        g
                        for g in self._get_prioritized_generators()
                        if (
                            g.name == source_id
                            and waste_type_enum in g.waste_streams
                            and g.waste_streams[waste_type_enum].volume > 0
                        )
                    ]
                case "treatment":
                    matching_generators = [
                        g
                        for g in self._get_prioritized_generators()
                        if (
                            waste_type_enum in g.waste_streams
                            and g.waste_streams[waste_type_enum].volume > 0
                        )
                    ]
                case _:
                    matching_generators = [
                        g
                        for g in self._get_prioritized_generators()
                        if (
                            waste_type_enum in g.waste_streams
                            and g.waste_streams[waste_type_enum].volume > 0
                        )
                    ]

            if matching_generators:
                for generator in matching_generators:
                    if self._find_available_vehicle():
                        self.collect_from_generator(generator, requested_volume=signal.get('volume'))

                        self.kanban_manager.acknowledge_signal(signal['id'])
                        break
                    else:
                        break  
            else:
                if source_type == "treatment":
                    self._propagate_signal_to_generators(signal, current_time)

                # Acknowledge the signal to prevent it from staying active forever
                self.kanban_manager.acknowledge_signal(signal['id'])

    def _propagate_signal_to_generators(self, signal, current_time):
        """Propagate demand signals upstream to generators"""
        waste_type_enum = signal['waste_type']

        state = SimulationState.get_instance()

        local_generators = [
            g for g in state.generators
            if (g.region_type == self.region_type and 
                waste_type_enum in g.waste_streams and
                g.inventory_policy == InventoryPolicy.PULL)  
        ]

        for generator in local_generators:
            generator.kanban_manager.add_signal(
                waste_type=waste_type_enum,
                timestamp=current_time,
                volume=signal['volume'],
                source_id=self.name,
                source_type="collector"
            )

    def should_collect(self) -> bool:
        utilization = self._calculate_utilization()

        if self.inventory_policy == InventoryPolicy.PUSH:
            base_threshold = self._get_adaptive_threshold()
            push_threshold = min(0.80, base_threshold + 0.10)  # +10% buffer for PUSH
            should = utilization < push_threshold
            return should

        elif self.inventory_policy == InventoryPolicy.PULL:
            # Market signals are downstream demand for treatment, not collection
            # requests (ADR 0002, Phase E); they must not trigger collection.
            signals = [
                s for s in self.kanban_manager.get_signals(self.env.now)
                if s.get('source_type') != "market"
            ]
            if signals:
                return True

            # PULL uses much lower thresholds
            base_threshold = self._get_adaptive_threshold()
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

    def collect_from_generator(self, generator, requested_volume=None):
        """Vehicle-based collection with proper overflow handling and storage management.

        ``requested_volume`` (PULL, ADR 0002 Phase E) bounds the pickup to the
        volume the downstream kanban signal actually asked for, so the collector
        replenishes to demand rather than grabbing a full vehicle load every
        trip. Without it (autonomous / PUSH collection) the pickup is the
        physical maximum, as before.
        """
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

        collection_center_available = (
            self.collection_center.waste_storage_capacity -
            sum(self.collection_center.current_storage.values())
        )

        if collection_center_available <= 0:
            available_vehicle.in_transit = False
            return self.env.process(self._dummy_process(0))

        clamps = [
            generator.current_storage,
            self.collection_capacity * self.efficiency,
            available_vehicle.capacity,
            collection_center_available,
        ]
        if requested_volume is not None:
            clamps.append(max(0.0, requested_volume))
        target_volume = min(clamps)

        if target_volume <= 0:
            available_vehicle.in_transit = False
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
        volume_prioritized = self._get_prioritized_generators()

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

    def provide_waste_for_treatment(self, requested_amount: float, needed_types: List[WasteType]) -> Dict[WasteType, float]:

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

    def _handle_completed_transport(self, transport: Dict) -> None:
        """Process a completed transport"""
        target_collector = next(
            (
                c
                for c in SimulationState.get_instance().collectors
                if c.region_type == transport["vehicle"].current_region
            ),
            None,
        )
        if target_collector:
            SimulationState.get_instance().track_add_waste(
                target_collector.region,
                transport["waste_type"],
                transport["volume"],
            )
            target_collector.collection_center.current_storage[
                transport["waste_type"]
            ] += transport["volume"]

    def _check_completed_transports(self, current_time: float) -> List[Dict]:
        """Identify completed transports and update vehicle status"""
        completed = []
        for transport in self.active_transports:
            if current_time >= transport["arrival_time"]:
                vehicle = transport["vehicle"]
                vehicle.in_transit = False
                vehicle.current_load = 0
                vehicle.current_region = vehicle.destination
                vehicle.destination = None
                vehicle.estimated_arrival = None
                completed.append(transport)
        return completed

    def _normalize_waste_type(self, waste_type_input) -> Optional[WasteType]:
        """Convert various waste type inputs to WasteType enum"""
        if isinstance(waste_type_input, WasteType):
            return waste_type_input

        if isinstance(waste_type_input, str):
            normalized = waste_type_input.replace(" ", "_").replace("-", "_").upper()
            try:
                return WasteType[normalized]
            except KeyError:
                pass

            waste_type_mapping = {
                "03_01_05": WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
                "15_01_03": WasteType.WOODEN_PACKAGING_15_01_03,
                "17_02_01": WasteType.CONSTRUCTION_WOOD_17_02_01,
                "03_01_01": WasteType.BARK_CORK_WASTE_03_01_01,
                "20_01_38": WasteType.NON_HAZARDOUS_WOOD_20_01_38,
                "15_01_01": WasteType.PAPER_PACKAGING_15_01_01,
            }
            return waste_type_mapping.get(waste_type_input)

        return None

    def _filter_active_waste_streams(self, generator) -> Dict[WasteType, any]:
        """Filter and convert generator waste streams to valid WasteType enums"""
        active_streams = {}

        for waste_type_str, stream in generator.waste_streams.items():
            if stream.volume <= 0:
                continue

            waste_type_enum = self._normalize_waste_type(waste_type_str)
            if not waste_type_enum:
                continue

            if (
                waste_type_enum in self.waste_types
                or waste_type_enum.value in self.waste_types
            ):
                active_streams[waste_type_enum] = stream

        return active_streams

    def _get_adaptive_threshold(self) -> float:
        """Get adaptive threshold that increases over time for ON_DEMAND"""
        base_time = self.env.now
        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                # Gradually increase threshold over time to trigger more collections
                time_factor = min(0.3, base_time * 0.001)  # Caps at 30%
                return 0.10 + time_factor  # Start at 10%, grow to 40%
            case StockStrategy.REORDER_50:
                return 0.50
            case StockStrategy.REORDER_90:
                return 0.90
            case _:
                raise ValueError(f"Unknown StockStrategy: {self.stock_strategy}")

    def _calculate_utilization(self) -> float:
        """Calculate storage utilization percentage"""
        storage_dict = self.collection_center.current_storage
        total_capacity = self.collection_center.waste_storage_capacity
        return (
            sum(storage_dict.values()) / total_capacity if total_capacity > 0 else 0.0
        )

    def _calculate_efficiency_multiplier(
        self, utilization: float, kanban_signals: int, base_time: float
    ) -> float:
        """Calculate efficiency multiplier based on policy and strategy"""
        base_degradation = max(0.5, 1.0 - (base_time * 0.0005))

        if self.inventory_policy == InventoryPolicy.PUSH:
            return self._calculate_push_efficiency(utilization, base_degradation)
        elif self.inventory_policy == InventoryPolicy.PULL:
            return self._calculate_pull_efficiency(
                utilization, kanban_signals, base_degradation
            )

        return base_degradation

    def _calculate_push_efficiency(self, utilization: float, base: float) -> float:
        """Calculate efficiency for PUSH policies with smooth curves"""

        utilization = max(0.0, min(1.0, utilization))

        match self.stock_strategy:
            case StockStrategy.REORDER_90:
                # Sweet spot around 85% utilization (80-90% range)
                if 0.8 <= utilization <= 0.9:
                    return base * 1.05  # Optimal efficiency
                else:
                    # Smooth degradation away from sweet spot
                    distance_from_optimal = abs(utilization - 0.85)
                    penalty = min(0.3, distance_from_optimal * 0.5)  # Max 30% penalty
                    return base * (1.0 - penalty)

            case StockStrategy.REORDER_50:
                # 50% strategy prefers moderate utilization (30-70% range)
                if 0.3 <= utilization <= 0.7:
                    return base * 1.0  # Normal efficiency
                elif utilization < 0.3:
                    # Penalty for underutilization
                    underutilization_penalty = (
                        0.3 - utilization
                    ) * 0.2  # Up to 6% penalty
                    return base * (1.0 - underutilization_penalty)
                else:
                    # Penalty for overutilization
                    overutilization_penalty = (
                        utilization - 0.7
                    ) * 0.15  # Up to 4.5% penalty
                    return base * (1.0 - overutilization_penalty)

            case StockStrategy.ON_DEMAND:
                # ON_DEMAND efficiency depends more on responsiveness than utilization
                if utilization < 0.1:
                    return base * 1.05  # Slight bonus for staying lean
                elif utilization > 0.8:
                    return base * 0.95  # Penalty for accumulating too much
                else:
                    return base

            case _:
                raise ValueError(f"Unknown StockStrategy: {self.stock_strategy}")

    def _calculate_pull_efficiency(
        self, utilization: float, signals: int, base: float
    ) -> float:
        """Calculate efficiency for PULL policies with signal responsiveness"""

        # Clamp utilization and signals to reasonable ranges
        utilization = max(0.0, min(1.0, utilization))
        signals = max(0, signals)

        match self.stock_strategy:
            case StockStrategy.ON_DEMAND:
                if signals == 0:
                    # No demand - minor efficiency loss (idle resources)
                    return base * 0.98
                else:
                    # More signals = better utilization of ON_DEMAND capabilities
                    signal_boost = min(
                        0.15, signals * 0.02
                    )  # Up to 15% efficiency gain

                    # Only physical constraints should limit efficiency
                    if utilization > 0.95:  # Very close to physical limits
                        strain = (utilization - 0.95) * 2.0  # Max 10% penalty at 100%
                        return base * (1.0 + signal_boost) * (1.0 - strain)
                    else:
                        return base * (1.0 + signal_boost)

            case StockStrategy.REORDER_90:
                # 90% reorder with PULL - benefits from signals but maintains buffer
                signal_bonus = min(0.1, signals * 0.02)  # Up to 10% bonus

                if utilization > 0.5:
                    buffer_bonus = 1.0  # Good buffer maintained
                else:
                    buffer_penalty = (0.5 - utilization) * 0.1  # Penalty for low buffer
                    buffer_bonus = 1.0 - buffer_penalty

                return base * (1.0 + signal_bonus) * buffer_bonus

            case StockStrategy.REORDER_50:
                # 50% reorder with PULL - balanced approach
                if signals > 0 and 0.3 <= utilization <= 0.7:
                    return base * 1.05  # Sweet spot
                elif signals == 0:
                    return base * 0.97  # Slight penalty for no demand signals
                else:
                    return base

            case _:
                return base

    def _get_prioritized_generators(self) -> List:
        """Get generators with 80% volume allocation to same region, 20% to next closest region"""

        state = SimulationState.get_instance()

        generators_with_waste = [g for g in state.generators if g.current_storage > 0]

        if not generators_with_waste:
            return []

        total_collection_capacity = self.collection_capacity * self.efficiency

        same_region_generators = [
            g for g in generators_with_waste if g.region_type == self.region_type
        ]

        other_region_generators = [
            g for g in generators_with_waste if g.region_type != self.region_type
        ]

        same_region_target = total_collection_capacity * LOCAL_COLLECTION_RATIO
        cross_region_target = total_collection_capacity * (1.0 - LOCAL_COLLECTION_RATIO)

        prioritized_generators = []

        if same_region_generators and same_region_target > 0:
            same_region_sorted = sorted(
                same_region_generators, key=lambda g: g.current_storage, reverse=True
            )

            selected_same_region = []
            accumulated_volume = 0

            for generator in same_region_sorted:
                if accumulated_volume >= same_region_target:
                    break

                collectible = min(
                    generator.current_storage, same_region_target - accumulated_volume
                )

                if collectible > 0:
                    selected_same_region.append(generator)
                    accumulated_volume += collectible

            prioritized_generators.extend(selected_same_region)

        if other_region_generators and cross_region_target > 0:
            closest_regions = get_closest_regions(
                self.region_type, n=3
            )  # Get top 3 closest

            for region_type, distance in closest_regions:
                region_generators = [
                    g for g in other_region_generators if g.region_type == region_type
                ]

                if region_generators:
                    region_sorted = sorted(
                        region_generators, key=lambda g: g.current_storage, reverse=True
                    )

                    selected_cross_region = []
                    accumulated_volume = 0

                    for generator in region_sorted:
                        if accumulated_volume >= cross_region_target:
                            break

                        collectible = min(
                            generator.current_storage,
                            cross_region_target - accumulated_volume,
                        )

                        if collectible > 0:
                            selected_cross_region.append(generator)
                            accumulated_volume += collectible

                    if selected_cross_region:
                        prioritized_generators.extend(selected_cross_region)
                        break

        return prioritized_generators
