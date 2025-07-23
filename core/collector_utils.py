from typing import List, Optional, Dict
from models.enums import WasteType
from models.data_classes import Vehicle, OperationalEntity
from models.state import SimulationState
from models.distances import get_distance
from utils.capacity_utils import apply_capacity_constraints, handle_overflow_with_decision

def get_available_vehicle(vehicles: List[Vehicle]) -> Optional[Vehicle]:
    """Get first available vehicle"""
    return next(
        (v for v in vehicles if not v.in_transit and v.current_load == 0 and v.destination is None), None
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
    if target_volume <= 0:
        return

    if collector2.region_type != collector1.region_type:
        # If different region, schedule transport
        success = collector1.transfer_waste_to_region(
            waste_type, target_volume, collector2.region_type
        )
        if success:
            # Track waste removal from current region
            SimulationState.get_instance().track_waste_collection(
                collector1.region, waste_type, target_volume
            )
    else:
        # Same region, check storage capacity
        result = apply_capacity_constraints(
            current_total=sum(collector2.collection_center.current_storage.values()),
            additional_amount=target_volume,
            capacity=collector2.collection_center.waste_storage_capacity
        )
        
        if result.allowed_amount > 0:
            # Update generator
            waste_stream.volume -= result.allowed_amount
            generator.current_storage -= result.allowed_amount

            # Update collector's storage
            collector2.collection_center.current_storage[waste_type] += result.allowed_amount
            collector2.collected_waste[waste_type] += result.allowed_amount
            remaining_capacity[collector2.name] -= result.allowed_amount

            # Track waste movement
            SimulationState.get_instance().track_waste_collection(
                generator.region, waste_type, result.allowed_amount
            )
            SimulationState.get_instance().track_waste_generation(
                collector2.region, waste_type, result.allowed_amount
            )

        if result.overflow_amount > 0:
            _, strategy = handle_overflow_with_decision(
                collector2,
                result.overflow_amount,
                collector2.region
            )
            collector2.waste_monitor.track_overflow(
                "collector",
                result.overflow_amount,
                strategy,
                collector2.env.now
            )

def get_prioritized_generators() -> List:
    """Get generators sorted by priority and filtered by region"""
    state = SimulationState.get_instance()
    regional_generators = [
        g
        for g in state.generators
        if g.current_storage > 0
    ]
    return regional_generators

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
        # First check collection capacity
        collection_result = apply_capacity_constraints(
            current_total=total_collected,
            additional_amount=min(
                stream.volume,
                collector.collection_capacity * collector.efficiency
            ),
            capacity=required_amount
        )

        if collection_result.allowed_amount > 0:
            # Update generator
            stream.volume -= collection_result.allowed_amount
            generator.current_storage -= collection_result.allowed_amount

            SimulationState.get_instance().track_waste_collection(
                generator.region, waste_type, collection_result.allowed_amount
            )

            collected_amounts[waste_type] += collection_result.allowed_amount
            total_collected += collection_result.allowed_amount

            if collection_result.overflow_amount > 0:
                _, strategy = handle_overflow_with_decision(
                    collector,
                    collection_result.overflow_amount,
                    collector.region
                )
                collector.waste_monitor.track_overflow(
                    "collector",
                    collection_result.overflow_amount,
                    strategy,
                    collector.env.now
                )

    return total_collected