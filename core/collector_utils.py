from typing import List, Optional, Tuple, Dict
from models.enums import WasteType, RegionType
from models.data_classes import Vehicle, OperationalEntity
from models.state import SimulationState
from models.distances import get_distance

def calculate_transport_route(
    region_type: RegionType, target_region: RegionType
) -> Tuple[List[RegionType], float]:
    """Calculate shortest path to target region and total distance"""
    if region_type == target_region:
        return [], 0.0

    distance = get_distance(region_type, target_region)
    return [target_region], distance

def get_available_vehicle(vehicles: List[Vehicle]) -> Optional[Vehicle]:
    """Get first available vehicle"""
    return next(
        (v for v in vehicles if not v.in_transit and v.current_load == 0), None
    )

def handle_completed_transport(transport: Dict, current_time: float) -> None:
    """Process a completed transport"""
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
            f"{current_time}: Added {transport['volume']:.8f} m³ to "
            f"{target_collector.name}'s collection center"
        )

def check_completed_transports(active_transports: List[Dict], current_time: float) -> List[Dict]:
    """Identify completed transports and update vehicle status"""
    completed = []
    for transport in active_transports:
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
    return completed

def handle_transport_delays(active_transports: List[Dict], current_time: float, rng) -> None:
    """Process potential delays for active transports"""
    for transport in active_transports:
        if (
            not transport["vehicle"].in_transit
            or current_time < transport["arrival_time"]
        ):
            continue

        # Simulate potential transport issues
        if rng.random() < 0.05:  # 5% chance of delay
            delay_hours = rng.uniform(1, 4)
            transport["arrival_time"] += delay_hours
            print(
                f"{current_time}: Transport delayed - Vehicle {transport['vehicle'].id} "
                f"new ETA: +{delay_hours:.1f} hours"
            )

def process_collection(
    collector: OperationalEntity,
    waste_type: WasteType,
    waste_stream,
    remaining_volume: float,
    remaining_capacity: Dict[str, float],
    generator,
    is_collaborative: bool = False,
) -> float:
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
            f"{collector.env.now}: {collector.name} {collection_type} {collectable_amount:.8f} m³ of {waste_type.value}"
        )

    return remaining_volume - collectable_amount

def handle_collector_capacity(
    collector1: OperationalEntity,
    collector2: OperationalEntity,
    waste_type: WasteType,
    target_volume: float,
    waste_stream,
    remaining_capacity: Dict[str, float],
    generator,
) -> None:
    """Handle waste collection for a specific collector"""
    if collector2.region_type != collector1.region_type:
        # If different region, schedule transport
        if target_volume > 0:
            success = collector1.transfer_waste_to_region(
                waste_type, target_volume, collector2.region_type
            )
            if success:
                # Track waste removal from current region
                SimulationState.get_instance().track_waste_collection(
                    collector1.region, waste_type, target_volume
                )
    else:
        # Same region, use normal collection process
        process_collection(
            collector2,
            waste_type,
            waste_stream,
            target_volume,
            remaining_capacity,
            generator,
            True,
        )

def collect_from_single_generator(
    collector: OperationalEntity,
    generator,
    required_amount: float,
    total_collected: float,
    collected_amounts: Dict[WasteType, float],
) -> float:
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
            collector.collection_capacity * collector.efficiency,
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
                collector.region, waste_type, collectable_amount
            )

            # Update collection center storage
            collector.collection_center.current_storage[waste_type] += collectable_amount
            collected_amounts[waste_type] += collectable_amount
            total_collected += collectable_amount

            print(
                f"{collector.env.now}: {collector.name} collected {collectable_amount:.8f} m³ of {waste_type.value} from {generator.name}"
            )

            # Immediately remove from collector storage since it's going to treatment
            collector.collection_center.current_storage[waste_type] -= collectable_amount

    return total_collected

def get_prioritized_generators() -> List:
    """Get generators sorted by priority and filtered by region"""
    state = SimulationState.get_instance()
    regional_generators = [
        g
        for g in state.generators
        if g.current_storage > 0
    ]

    regional_generators.sort(key=lambda x: x.priority_level, reverse=True)
    return regional_generators

def handle_competitive_collection(collector: OperationalEntity, prioritized_generators: List) -> float:
    """Handle competitive collection strategy"""
    if prioritized_generators and collector.availability:
        return collector.collect_from_generator(prioritized_generators[0])
    return 0

def handle_collaborative_collection(collector: OperationalEntity, prioritized_generators: List) -> float:
    """Handle collaborative collection strategy"""
    if not collector.availability:
        return 0

    state = SimulationState.get_instance()
    other_collectors = [
        c
        for c in state.collectors
        if c != collector and c.availability and c.region_type == collector.region_type
    ]

    total_collection_cost = 0
    for generator in prioritized_generators:
        if generator.current_storage <= 0:
            continue
        collector.collect_with_collaboration(generator, other_collectors)
        total_collection_cost += collector.transport_cost
    return total_collection_cost
