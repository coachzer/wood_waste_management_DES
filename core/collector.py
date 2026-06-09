import numpy as np
from typing import Dict, List, Optional
from config.constants import (
    TRANSPORT_EMISSIONS_PER_TON_KM,
    KILOGRAMS_PER_TONNE,
    WASTE_DENSITIES,
    FAILED_ENTITY_EFFICIENCY,
    TRAVEL_SPEED_KMH,
    LOCAL_COLLECTION_RATIO,
    COLLECTION_COST_PER_KM_PER_M3,
    ESTIMATED_COLLECTION_COST_PER_KM,
)
from core.transport_manager import PointToPointTransport, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from instrumentation.waste_monitor import WasteMonitor
from models.data_classes import Vehicle, CollectionCenter, OperationalEntity
from models.distances import REGION_COORDINATES, get_distance, get_closest_regions
from utils.capacity_utils import (
    handle_storage_event,
    check_storage_capacity,
    split_overflow_by_type,
)
from core.kanban_manager import KanbanManager
from core.strategies import build_stock_strategy, build_inventory_policy

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
        stock_strategy_behavior = None,
        inventory_policy_behavior = None,
        transport_manager: PointToPointTransport = None,
        state = None,
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
        self.state = state
        self.inventory_policy = inventory_policy
        self.stock_strategy = stock_strategy
        self.stock_strategy_behavior = stock_strategy_behavior or build_stock_strategy(stock_strategy)
        self.inventory_policy_behavior = inventory_policy_behavior or build_inventory_policy(inventory_policy)
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
                capacity=self.vehicle_capacity,
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

            vehicle.current_load = collected_amount
            vehicle.current_load_by_type = dict(collected_waste)
            yield self.env.timeout(travel_time)

            self._add_to_collection_center(collected_waste)
            collection_cost = self.transport_cost + (distance * COLLECTION_COST_PER_KM_PER_M3 * collected_amount)
            self.last_collection_cost = collection_cost

            # Transport emissions: each stream's volume is converted to mass at its
            # own bulk density (WASTE_DENSITIES, kg/m³) before the per-ton-km factor
            # applies (ADR 0013). Sorted by WasteType.value so the summation order is
            # deterministic across processes (CRN guard).
            emissions = sum(
                volume_m3 * (WASTE_DENSITIES[waste_type] / KILOGRAMS_PER_TONNE)
                * distance * TRANSPORT_EMISSIONS_PER_TON_KM
                for waste_type, volume_m3 in sorted(
                    collected_waste.items(), key=lambda item: item[0].value
                )
            )

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
                    environmental_impact=emissions,
                    timestamp=self.env.now,
                    impact_category="transport_emissions"
                )
        else:
            yield self.env.timeout(travel_time)
            collection_cost = self.transport_cost

        vehicle.in_transit = False
        vehicle.current_load = 0
        vehicle.current_load_by_type = {}
        vehicle.destination = self.region_type

        return collection_cost

    def _perform_collection_at_site(self, generator, target_volume):
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
            # check_storage_capacity already scaled each type proportionally, so the
            # per-type overflow is exactly what was skimmed off each stream. Sorted by
            # WasteType.value for deterministic iteration (CRN guard).
            per_type_overflow = {
                waste_type: potential_collections[waste_type]
                - allowed_collections.get(waste_type, 0.0)
                for waste_type in sorted(
                    potential_collections, key=lambda waste_type: waste_type.value
                )
            }
            handle_storage_event(generator, per_type_overflow)

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

            self.state.track_remove_waste(
                generator.region, waste_type, amount
            )

            self.state.track_transport_flow(
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
            overflow_amount = total_to_add - available_space

            # handle_storage_event decides expand vs landfill; on the expand branch
            # store what now fits and landfill the remainder, so every collected m3
            # is stored or landfilled, none silently dropped (ADR 0009).
            _cost, action = handle_storage_event(
                self, split_overflow_by_type(collected_waste, overflow_amount)
            )

            if action == "expand_storage":
                storable = min(
                    total_to_add,
                    self.collection_center.waste_storage_capacity - current_total,
                )
                handle_storage_event(
                    self,
                    split_overflow_by_type(collected_waste, total_to_add - storable),
                    force_landfill=True,
                )
            else:
                storable = available_space

            scaling_factor = storable / total_to_add if total_to_add > 0 else 0
            for waste_type, amount in collected_waste.items():
                self.collection_center.current_storage[waste_type] += amount * scaling_factor

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

            # PULL with pending signals skips the jitter draw; the signal read is
            # a callable because ``get_signals`` prunes stale signals as a side
            # effect and PUSH must not trigger it (it short-circuited before).
            timeout = self.inventory_policy_behavior.collection_timeout(
                base_timeout=self.collection_frequency,
                has_signals_fn=lambda: bool(self.kanban_manager.get_signals(self.env.now)),
                rng=self.rng,
            )

            yield self.env.timeout(timeout)

            if not self.should_collect():
                continue

            kanban_signals = [
                s for s in self.kanban_manager.get_signals(self.env.now)
                if s.get('source_type') != "market"
            ]
            if self.inventory_policy_behavior.should_process_kanban_signals(kanban_signals):
                self._process_kanban_signals(kanban_signals)
            else:
                # Regular collection based on policy
                self._unified_collection_strategy()

    def _process_kanban_signals(self, signals):
        """Process signals with acknowledgment and cross-region support"""
        for signal in signals:
            # Market signals (source_type="market") are downstream demand for
            # treatment production (ADR 0002, Phase E), not waste-collection
            # requests; collectors must not consume them or they starve the
            # treatment operator's production loop (its sole consumer).
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

        state = self.state

        local_generators = [
            g for g in state.generators
            if (g.region_type == self.region_type and
                waste_type_enum in g.waste_streams and
                g.inventory_policy.is_pull())
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
        # The non-market signal read is wrapped in a callable because
        # ``get_signals`` prunes stale signals as a side effect: only the PULL
        # path consulted it, so PUSH must not trigger it. The adaptive threshold
        # is pure, so computing it eagerly is observationally identical.
        return self.inventory_policy_behavior.collector_should_collect(
            utilization=self._calculate_utilization(),
            adaptive_threshold=self.stock_strategy_behavior.collector_adaptive_threshold(self.env.now),
            non_market_signals_fn=lambda: [
                s for s in self.kanban_manager.get_signals(self.env.now)
                if s.get('source_type') != "market"
            ],
        )

    def transfer_waste_to_region(self, waste_type: WasteType, volume: float, destination: RegionType) -> bool:
        """Updated method using point-to-point transport"""
        if volume <= 0:
            return False

        if self.collection_center.current_storage[waste_type] < volume:
            return False

        request = TransportRequest(
            origin=self.region_type,
            destination=destination,
            waste_type=waste_type,
            volume=volume,
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

        if generator.current_storage <= 0:
            return self.env.process(self._dummy_process(0))

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

        return self.env.process(self._dispatch_vehicle_for_collection(available_vehicle, generator, target_volume))

    def _dummy_process(self, return_value):
        """Helper for SimPy process returns"""
        yield self.env.timeout(0)
        return return_value

    def _unified_collection_strategy(self) -> float:
        """Strategy with 80/20 volume allocation between same/cross regions"""
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
            estimated_cost = self.transport_cost + (distance * ESTIMATED_COLLECTION_COST_PER_KM)
            total_cost += estimated_cost

        return total_cost

    def provide_waste_for_treatment(self, requested_amount: float, needed_types: List[WasteType],
                                     treatment_name: Optional[str] = None) -> Dict[WasteType, float]:
        """Hand waste from this collector's collection center to a treatment operator.

        The real Treatment-echelon inbound flow (ADR 0009): decrements collector
        storage, feeds the treatment process, and logs each transferred type as a
        ``collector -> treatment`` transport flow so the bullwhip Treatment echelon
        reads actual replenishment, not the net-zero repositioning move.
        ``treatment_name`` names the receiving operator (the flow target).
        """
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

                if treatment_name is not None:
                    self.state.track_transport_flow(
                        source_type="collector",
                        source_name=self.name,
                        target_type="treatment",
                        target_name=treatment_name,
                        waste_type=waste_type,
                        volume=transfer_amount,
                        timestamp=self.env.now,
                        transport_method="treatment_intake",
                    )

        return provided_waste

    def _handle_completed_transport(self, transport: Dict) -> None:
        """Process a completed transport"""
        target_collector = next(
            (
                c
                for c in self.state.collectors
                if c.region_type == transport["vehicle"].current_region
            ),
            None,
        )
        if target_collector:
            self.state.track_add_waste(
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
                vehicle.current_load_by_type = {}
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
        return self.inventory_policy_behavior.collector_efficiency(
            self.stock_strategy_behavior, utilization, kanban_signals, base_degradation
        )

    def _get_prioritized_generators(self) -> List:
        """Get generators with 80% volume allocation to same region, 20% to next closest region"""

        state = self.state

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
