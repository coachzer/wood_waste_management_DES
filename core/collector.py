from typing import Dict, List, Optional
from config.constants import (
    TRANSPORT_EMISSIONS_PER_TON_KM,
    KILOGRAMS_PER_TONNE,
    WASTE_DENSITIES,
    TRAVEL_SPEED_KMH,
    SAME_REGION_COLLECTION_DISTANCE_KM,
    SAME_REGION_DISTANCE_VARIATION_RANGE,
    LOCAL_COLLECTION_RATIO,
    COLLECTION_COST_PER_KM_PER_M3,
    ROAD_CIRCUITY_FACTOR,
    ESTIMATED_COLLECTION_COST_PER_KM,
    COLLECTOR_DEGRADATION_FLOOR,
    COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY,
    OPERATING_TICK_DAYS,
    COLLECTOR_TRIP_COST_CAP,
    COLLECTION_CENTER_CAPACITY_MULTIPLE,
    VEHICLES_PER_COLLECTOR,
)
from core.transport_manager import PointToPointTransport, TransportRequest
from models.enums import InventoryPolicy, WasteType, RegionType, EntityStatus, StockStrategy
from instrumentation.waste_monitor import WasteMonitor
from models.data_classes import FailureConfig, Vehicle, CollectionCenter, OperationalEntity
from config.base_config import ScenarioConfig
from models.distances import get_distance, get_closest_regions
from utils.capacity_utils import (
    handle_storage_event,
    check_storage_capacity,
    compute_and_handle_overflow,
    split_overflow_by_type,
    per_tick_capacity,
)
from core.kanban_manager import KanbanManager
from core.strategies import build_stock_strategy, build_inventory_policy


def _is_market_signal(signal) -> bool:
    return signal.get('source_type') == "market"


def _is_addressed_to_other_region(signal, region_type) -> bool:
    target_region = signal.get('target_region')
    return target_region is not None and target_region != region_type

class CollectorCompany(OperationalEntity):
    """A company that collects waste from generators"""

    @property
    def waste_storage_capacity(self):
        return self.collection_center.waste_storage_capacity

    @waste_storage_capacity.setter
    def waste_storage_capacity(self, value):
        self.collection_center.waste_storage_capacity = value

    def __init__(
        self,
        env,
        name,
        waste_types,
        collection_capacity,
        collection_frequency,
        transport_cost,
        efficiency,
        availability,
        region_type: RegionType,
        scenario: ScenarioConfig,
        waste_monitor: WasteMonitor,
        kanban_manager: KanbanManager,
        inventory_policy: InventoryPolicy,
        stock_strategy: StockStrategy,
        transport_manager: PointToPointTransport,
        state,
        failure_config: Optional[FailureConfig],
        seed,
        vehicle_capacity: Optional[float] = None,
    ):
        self.scenario = scenario
        super().__init__(failure_config=failure_config, seed=seed)
        self.env = env
        self.name = name
        self.facility_type = "collector"
        self.expansion_count = 0
        self.waste_types = set(waste_types) if waste_types else set()
        self.kanban_manager = kanban_manager
        self.state = state
        self.inventory_policy = inventory_policy
        self.stock_strategy = stock_strategy
        self.stock_strategy_behavior = build_stock_strategy(stock_strategy)
        self.inventory_policy_behavior = build_inventory_policy(inventory_policy)
        self.transport_manager = transport_manager
        self.collection_frequency = collection_frequency
        self.initial_collection_capacity_per_tick_m3 = per_tick_capacity(
            collection_capacity, collection_frequency
        )
        self.collection_capacity_per_tick_m3 = self.initial_collection_capacity_per_tick_m3
        self.initial_transport_cost = transport_cost
        self.transport_cost = transport_cost
        self.last_collection_cost = 0.0
        self.efficiency = efficiency
        self.status = EntityStatus.OPERATIONAL if availability else EntityStatus.FAILED
        self.region_type = region_type

        self.collection_center = CollectionCenter(
            waste_storage_capacity=collection_capacity * COLLECTION_CENTER_CAPACITY_MULTIPLE,
            current_storage=dict.fromkeys(WasteType, 0.0),
        )

        self.vehicle_capacity = (
            vehicle_capacity if vehicle_capacity is not None else self.initial_collection_capacity_per_tick_m3
        )
        self.vehicles = [
            Vehicle(
                id=f"{self.name}_vehicle_{i}",
                capacity=self.vehicle_capacity,
                current_region=self.region_type,
            )
            for i in range(VEHICLES_PER_COLLECTOR)
        ]

        self.active_transports = []
        self.returning_vehicles = []

        self.collected_waste = dict.fromkeys(WasteType, 0.0)

        self.waste_monitor = waste_monitor

        self.process = env.process(self.collection_loop())
        env.process(self.manage_transport())
        self.start_failure_process(env)

    def _find_available_vehicle(self):
        """Find an available vehicle for collection"""
        return next((v for v in self.vehicles if not v.in_transit), None)

    def _sample_transport_circuity(self):
        """Per-trip road-circuity factor on the great-circle distance (ADR 0015).

        Drawn from Normal(mean, std) of the scenario's transportation_time,
        clamped to at least 1.0 -- a road cannot be shorter than the
        great-circle line. Affects travel time only; cost and emissions use
        ROAD_CIRCUITY_FACTOR (ADR 0038).
        """
        circuity_mean, circuity_std = self.scenario.transportation_time
        return max(1.0, self.rng.normal(circuity_mean, circuity_std))

    def _calculate_travel_time_to_generator(self, generator):
        """Calculate travel time to generator (simplified)"""

        if generator.region_type == self.region_type:
            distance_variation = self.rng.uniform(*SAME_REGION_DISTANCE_VARIATION_RANGE)
            distance = SAME_REGION_COLLECTION_DISTANCE_KM * distance_variation
        else:
            distance = get_distance(self.region_type, generator.region_type)

        travel_time_hours = distance * self._sample_transport_circuity() / TRAVEL_SPEED_KMH
        travel_time_days = travel_time_hours / 24.0
        return travel_time_days, distance

    def _dispatch_vehicle_for_collection(self, vehicle, generator, target_volume, waste_type=None):
        """Complete vehicle collection process with proper storage and overflow handling"""
        current_time = self.env.now

        travel_time, distance = self._calculate_travel_time_to_generator(generator)

        vehicle.in_transit = True
        vehicle.destination = generator.region_type
        vehicle.estimated_arrival = current_time + travel_time

        yield self.env.timeout(travel_time)

        collected_amount, collected_waste = self._perform_collection_at_site(generator, target_volume, waste_type)

        if collected_amount > 0:

            vehicle.current_load_by_type = dict(collected_waste)
            yield self.env.timeout(travel_time)

            self._add_to_collection_center(collected_waste)
            collection_cost = self.charge_trip(collected_waste, distance)
            self.last_collection_cost = collection_cost
        else:
            yield self.env.timeout(travel_time)
            collection_cost = self.transport_cost

        vehicle.in_transit = False
        vehicle.current_load_by_type = {}
        vehicle.destination = self.region_type

        return collection_cost

    def charge_trip(self, load_by_type, distance):
        """Charge one loaded trip: fixed trip cost plus per road km per m3, and ton-km emissions.

        ``distance`` is great-circle; cost and emissions use road km (ADR 0038).
        """
        road_distance = distance * ROAD_CIRCUITY_FACTOR
        trip_cost = self.transport_cost + (road_distance * COLLECTION_COST_PER_KM_PER_M3 * sum(load_by_type.values()))
        emissions = sum(
            volume_m3 * (WASTE_DENSITIES[waste_type] / KILOGRAMS_PER_TONNE)
            * road_distance * TRANSPORT_EMISSIONS_PER_TON_KM
            for waste_type, volume_m3 in sorted(
                load_by_type.items(), key=lambda item: item[0].value
            )
        )

        if self.waste_monitor:
            self.waste_monitor.update_entity_costs(
                entity_name=self.name,
                entity_type=self.facility_type,
                energy_cost=0.0,
                processing_cost=0.0,
                transport_cost=trip_cost
            )
            self.waste_monitor.record_emission(
                entity_name=self.name,
                kind="transport_emissions",
                kgco2e=emissions,
                timestamp=self.env.now,
            )
        return trip_cost

    def _perform_collection_at_site(self, generator, target_volume, waste_type=None):
        """Collect at the generator site; only ``waste_type`` when a signal names one (ADR 0028)."""
        active_streams = self._filter_active_waste_streams(generator)
        if waste_type is not None:
            active_streams = {
                stream_type: stream for stream_type, stream in active_streams.items() if stream_type == waste_type
            }

        if not active_streams:
            return 0, {}

        potential_collections = {}
        remaining_capacity = target_volume

        for waste_type, stream in active_streams.items():
            if remaining_capacity <= 0:
                break

            collectible_amount = min(
                stream.volume,
                self.collection_capacity_per_tick_m3,
                remaining_capacity
            )

            if collectible_amount > 0:
                potential_collections[waste_type] = collectible_amount
                remaining_capacity -= collectible_amount

        if not potential_collections:
            return 0, {}

        allowed_collections, overflow = check_storage_capacity(
            {},
            potential_collections,
            target_volume
        )

        if overflow > 0:
            compute_and_handle_overflow(
                generator, potential_collections, allowed_collections
            )

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

            new_transports = self.transport_manager.process_requests(current_time)
            self.active_transports.extend(new_transports)

            completed = self._check_completed_transports(current_time)

            for transport in completed:
                self._handle_completed_transport(transport)
                self.active_transports.remove(transport)

            yield self.env.timeout(1.0)

    def _apply_status_throughput_effects(self):
        """FAILED floors efficiency; RECOVERING ramps it back via recovery progress."""
        if self.status in (EntityStatus.FAILED, EntityStatus.RECOVERING):
            self.efficiency = self.get_operational_efficiency()

    def update_efficiency(self):
        """Equipment aging only; the same for every policy and strategy (ADR 0025)."""
        current_time = self.env.now
        self.efficiency = max(
            COLLECTOR_DEGRADATION_FLOOR,
            1.0 - (current_time * COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY),
        )

    def collection_loop(self):
        """Periodically collect waste from generators based on strategy"""
        while True:

            current_time = self.env.now

            self.update_efficiency()

            if self.apply_failure_tick():
                yield self.env.timeout(OPERATING_TICK_DAYS)
                continue

            self.collection_capacity_per_tick_m3 = self.initial_collection_capacity_per_tick_m3 * self.efficiency
            self.transport_cost = min(COLLECTOR_TRIP_COST_CAP, self.initial_transport_cost * (2 - self.efficiency))

            yield self.env.timeout(OPERATING_TICK_DAYS)

            if not self.should_collect():
                continue

            kanban_signals = self._non_market_signals()
            if self.inventory_policy_behavior.should_process_kanban_signals(kanban_signals):
                self._process_kanban_signals(kanban_signals)
            else:
                self._unified_collection_strategy()

    def _signals_in_dispatch_order(self, signals):
        """Order signals for the vehicles this tick (ADR 0031).

        Treatment signals go first, largest volume first, so tiny orders do not use up the
        vehicles. Treatment re-posts its full gap every tick, so only the newest signal per
        operator and waste type is live; older ones are acknowledged here.
        """
        newest_treatment_signals = {}
        other_signals = []
        for signal in signals:
            if _is_market_signal(signal) or _is_addressed_to_other_region(signal, self.region_type):
                continue
            if signal.get('source_type') != "treatment":
                other_signals.append(signal)
                continue
            key = (signal['source_id'], signal['waste_type'])
            previous = newest_treatment_signals.get(key)
            if previous is not None:
                older, signal = sorted([previous, signal], key=lambda candidate: candidate['timestamp'])
                self.kanban_manager.acknowledge_signal(older['id'])
            newest_treatment_signals[key] = signal
        by_volume_descending = lambda signal: -(signal.get('volume') or 0.0)
        return (
            sorted(newest_treatment_signals.values(), key=by_volume_descending)
            + sorted(other_signals, key=by_volume_descending)
        )

    def _process_kanban_signals(self, signals):
        """Process signals with acknowledgment and cross-region support"""
        for signal in self._signals_in_dispatch_order(signals):

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
                        self.collect_from_generator(
                            generator, requested_volume=signal.get('volume'), waste_type=waste_type_enum
                        )

                        self.kanban_manager.acknowledge_signal(signal['id'])
                        break
                    else:
                        break
            elif source_type != "generator":
                if source_type == "treatment":
                    self._propagate_signal_to_generators(signal, current_time)

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
        return self.inventory_policy_behavior.collector_should_collect(
            utilization=self._calculate_utilization(),
            adaptive_threshold=self.stock_strategy_behavior.collector_adaptive_threshold(self.env.now),
            non_market_signals_fn=self._non_market_signals,
        )

    def _non_market_signals(self):
        return [
            signal for signal in self.kanban_manager.get_signals(self.env.now)
            if not _is_market_signal(signal)
        ]

    def transferable_volume(self, waste_type: WasteType) -> float:
        """Stock of this waste type not yet claimed by a queued transfer."""
        return (self.collection_center.current_storage[waste_type]
                - self.transport_manager.queued_volume(self.name, waste_type))

    def transfer_waste_to_region(self, waste_type: WasteType, volume: float, destination: RegionType):
        """Queue a transfer; the volume stays in this center until a vehicle loads it."""
        self.transport_manager.request_transport(TransportRequest(
            origin=self.region_type,
            destination=destination,
            waste_type=waste_type,
            volume=volume,
            request_time=self.env.now,
            requester_id=self.name,
        ))

    def collect_from_generator(self, generator, requested_volume=None, waste_type=None):
        """Vehicle-based collection with proper overflow handling and storage management.

        ``requested_volume`` and ``waste_type`` (PULL, ADR 0002 Phase E, ADR 0028)
        bound the pickup to what the kanban signal asked for: that volume of
        that type. Without them (PUSH) the pickup is the physical maximum of
        every stream.
        """
        if self.status == EntityStatus.FAILED:
            return

        if generator.current_storage <= 0:
            return

        available_vehicle = self._find_available_vehicle()
        if not available_vehicle:
            return

        available_vehicle.in_transit = True

        collection_center_available = (
            self.collection_center.waste_storage_capacity -
            sum(self.collection_center.current_storage.values())
        )

        if collection_center_available <= 0:
            available_vehicle.in_transit = False
            return

        if waste_type is not None:
            available_at_generator = generator.waste_streams[waste_type].volume
        else:
            available_at_generator = generator.current_storage
        clamps = [
            available_at_generator,
            self.collection_capacity_per_tick_m3,
            available_vehicle.capacity,
            collection_center_available,
        ]
        if requested_volume is not None:
            clamps.append(max(0.0, requested_volume))
        target_volume = min(clamps)

        if target_volume <= 0:
            available_vehicle.in_transit = False
            return

        self.env.process(
            self._dispatch_vehicle_for_collection(available_vehicle, generator, target_volume, waste_type)
        )

    def _unified_collection_strategy(self) -> float:
        """Strategy with 80/20 volume allocation between same/cross regions"""
        volume_prioritized = self._get_prioritized_generators()

        total_cost = 0

        for generator in volume_prioritized:
            if generator.current_storage <= 0:
                continue

            if not self._find_available_vehicle():
                break

            self.collect_from_generator(generator)

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
                if c.region_type == transport["destination"]
            ),
            None,
        )
        if target_collector:
            target_collector.collection_center.current_storage[
                transport["waste_type"]
            ] += transport["volume"]
        transport["collector"].charge_trip(
            {transport["waste_type"]: transport["volume"]},
            get_distance(transport["origin"], transport["destination"]),
        )

    def _check_completed_transports(self, current_time: float) -> List[Dict]:
        """Identify delivered transports, send their vehicles home empty, and free vehicles back home.

        The return leg takes road travel time and is covered by the fixed trip cost (ADR 0040).
        """
        completed = []
        for transport in self.active_transports:
            if current_time >= transport["arrival_time"]:
                vehicle = transport["vehicle"]
                home_region = transport["collector"].region_type
                vehicle.current_load_by_type = {}
                vehicle.current_region = transport["destination"]
                vehicle.destination = home_region
                vehicle.estimated_arrival = transport["arrival_time"] + self.transport_manager.travel_time_days(
                    transport["destination"], home_region)
                self.returning_vehicles.append(vehicle)
                completed.append(transport)

        for vehicle in list(self.returning_vehicles):
            if current_time >= vehicle.estimated_arrival:
                vehicle.in_transit = False
                vehicle.current_region = vehicle.destination
                vehicle.destination = None
                vehicle.estimated_arrival = None
                self.returning_vehicles.remove(vehicle)
        return completed

    def _filter_active_waste_streams(self, generator) -> Dict[WasteType, any]:
        """The generator's non-empty streams of waste types this collector handles."""
        return {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0 and waste_type in self.waste_types
        }

    def _calculate_utilization(self) -> float:
        """Calculate storage utilization percentage"""
        storage_dict = self.collection_center.current_storage
        total_capacity = self.collection_center.waste_storage_capacity
        return (
            sum(storage_dict.values()) / total_capacity if total_capacity > 0 else 0.0
        )

    @staticmethod
    def _select_generators_up_to_volume(generators: List, target_volume: float) -> List:
        """Pick generators by descending storage until their collectible sum meets the target."""
        generators_sorted = sorted(
            generators, key=lambda g: g.current_storage, reverse=True
        )

        selected = []
        accumulated_volume = 0

        for generator in generators_sorted:
            if accumulated_volume >= target_volume:
                break

            collectible = min(
                generator.current_storage, target_volume - accumulated_volume
            )

            if collectible > 0:
                selected.append(generator)
                accumulated_volume += collectible

        return selected

    def _get_prioritized_generators(self) -> List:
        """Get generators with 80% volume allocation to same region, 20% to next closest region"""

        state = self.state

        generators_with_waste = [g for g in state.generators if g.current_storage > 0]

        if not generators_with_waste:
            return []

        total_collection_capacity = self.collection_capacity_per_tick_m3

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
            prioritized_generators.extend(
                self._select_generators_up_to_volume(
                    same_region_generators, same_region_target
                )
            )

        if other_region_generators and cross_region_target > 0:
            closest_regions = get_closest_regions(
                self.region_type, n=3
            )

            for region_type, distance in closest_regions:
                region_generators = [
                    g for g in other_region_generators if g.region_type == region_type
                ]

                if region_generators:
                    selected_cross_region = self._select_generators_up_to_volume(
                        region_generators, cross_region_target
                    )

                    if selected_cross_region:
                        prioritized_generators.extend(selected_cross_region)
                        break

        return prioritized_generators
