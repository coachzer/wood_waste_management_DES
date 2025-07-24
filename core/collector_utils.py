from typing import List, Dict, Optional
from models.enums import InventoryPolicy, StockStrategy, WasteType
from models.data_classes import OperationalEntity
from models.state import SimulationState
from utils.capacity_utils import apply_capacity_constraints, handle_overflow_with_decision

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
                facility_type="collector",
                volume=result.overflow_amount,
                strategy=strategy,
                timestamp=collector2.env.now,
                region=collector2.region
            )

def normalize_waste_type(waste_type_input) -> Optional[WasteType]:
    """Convert various waste type inputs to WasteType enum"""
    if isinstance(waste_type_input, WasteType):
        return waste_type_input
    
    if isinstance(waste_type_input, str):
        # Try direct enum lookup
        normalized = waste_type_input.replace(" ", "_").replace("-", "_").upper()
        try:
            return WasteType[normalized]
        except KeyError:
            pass
        
        # Fallback mapping for common cases
        waste_type_mapping = {
            "03_01_05": WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
            "15_01_03": WasteType.WOODEN_PACKAGING_15_01_03,
            "17_02_01": WasteType.CONSTRUCTION_WOOD_17_02_01,
            "03_01_01": WasteType.BARK_WASTE_03_01_01,
            "20_01_38": WasteType.NON_HAZARDOUS_WOOD_20_01_38,
            "15_01_01": WasteType.PAPER_PACKAGING_15_01_01
        }
        return waste_type_mapping.get(waste_type_input)
    
    return None

def filter_active_waste_streams(generator, collector_waste_types: set) -> Dict[WasteType, any]:
    """Filter and convert generator waste streams to valid WasteType enums"""
    active_streams = {}
    
    for waste_type_str, stream in generator.waste_streams.items():
        if stream.volume <= 0:
            continue
            
        waste_type_enum = normalize_waste_type(waste_type_str)
        if not waste_type_enum:
            continue
            
        # Check if collector handles this waste type
        if (waste_type_enum in collector_waste_types or 
            waste_type_enum.value in collector_waste_types):
            active_streams[waste_type_enum] = stream
    
    return active_streams

def get_adaptive_threshold(strategy: StockStrategy, base_time: float) -> float:
    """Get adaptive threshold that increases over time for ON_DEMAND"""
    if strategy == StockStrategy.ON_DEMAND:
        # Gradually increase threshold over time to trigger more collections
        time_factor = min(0.3, base_time * 0.001)  # Caps at 30%
        return 0.05 + time_factor  # Start at 5%, grow to 35%
    elif strategy == StockStrategy.REORDER_50:
        return 0.50
    elif strategy == StockStrategy.REORDER_90:
        return 0.90
    # elif strategy == StockStrategy.FULL_STOCK:
    #     return 0.95
    return 0.10

def calculate_utilization(storage_dict: Dict, total_capacity: float) -> float:
    """Calculate storage utilization percentage"""
    return sum(storage_dict.values()) / total_capacity if total_capacity > 0 else 0.0

def calculate_efficiency_multiplier(policy: InventoryPolicy, strategy: StockStrategy, 
                                 utilization: float, kanban_signals: int, 
                                 base_time: float) -> float:
    """Calculate efficiency multiplier based on policy and strategy"""
    base_degradation = max(0.5, 1.0 - (base_time * 0.0005))
    
    if policy == InventoryPolicy.PUSH:
        return _calculate_push_efficiency(strategy, utilization, base_degradation)
    elif policy == InventoryPolicy.PULL:
        return _calculate_pull_efficiency(strategy, utilization, kanban_signals, base_degradation)
    
    return base_degradation

def _calculate_push_efficiency(strategy: StockStrategy, utilization: float, base: float) -> float:
    """Calculate efficiency for PUSH policies"""

    match strategy:
        case StockStrategy.REORDER_90:
            print(f"Strategy: {strategy}, Utilization: {utilization}, Base: {base}  ")
            if 0.8 <= utilization <= 0.9:
                return base * 1.05  # Sweet spot
            else:
                return base * (1.0 - abs(utilization - 0.85) * 0.1)
        case StockStrategy.REORDER_50:
            print(f"Strategy: {strategy}, Utilization: {utilization}, Base: {base}  ")
            penalty = 0.95 if utilization < 0.3 else 1.0
            return base * penalty
        # case StockStrategy.FULL_STOCK:
        #     storage_penalty = utilization * 0.05
        #     return base * (1.0 - storage_penalty)
        case _: # StockStrategy.ON_DEMAND:
            print(f"Strategy: {strategy}, Utilization: {utilization}, Base: {base}  ")
            return base

def _calculate_pull_efficiency(strategy: StockStrategy, utilization: float, 
                              signals: int, base: float) -> float:
    """Calculate efficiency for PULL policies"""
    if strategy == StockStrategy.ON_DEMAND:
        if signals > 0 and utilization < 0.2:
            return base * 1.1  # Responsive and lean
        elif signals > 3:
            return base * 0.9  # Overwhelmed
        return base
    elif strategy == StockStrategy.REORDER_90:
        signal_bonus = min(1.1, 1.0 + (signals * 0.02))
        buffer_penalty = 1.0 if utilization > 0.5 else 0.95
        return base * signal_bonus * buffer_penalty
    elif strategy == StockStrategy.REORDER_50:
        if signals > 0 and 0.3 <= utilization <= 0.7:
            return base * 1.05
        return base
    return base

def get_prioritized_generators() -> List:
    """Get generators sorted by priority and filtered by region"""
    state = SimulationState.get_instance()
    regional_generators = [
        g
        for g in state.generators
        if g.current_storage > 0
    ]
    return regional_generators

