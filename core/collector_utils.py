from typing import List, Dict, Optional
from models.distances import get_closest_regions
from models.enums import InventoryPolicy, StockStrategy, WasteType
from models.state import SimulationState

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

def get_prioritized_generators(collector) -> List:
    """
    Get generators with 80% volume allocation to same region, 20% to next closest region
    
    Args:
        collector: The collector instance with region and capacity information
        
    Returns:
        List of generators prioritized by volume allocation strategy
    """
    
    state = SimulationState.get_instance()
    
    # Filter generators with available storage
    generators_with_waste = [
        g for g in state.generators
        if g.current_storage > 0
    ]
    
    if not generators_with_waste:
        return []
    
    # Calculate collector's total collection capacity for this cycle
    total_collection_capacity = collector.collection_capacity * collector.efficiency
    
    # Separate generators by region
    same_region_generators = [
        g for g in generators_with_waste 
        if g.region_type == collector.region_type
    ]
    
    other_region_generators = [
        g for g in generators_with_waste 
        if g.region_type != collector.region_type
    ]
    
    # Calculate volume allocations
    same_region_target = total_collection_capacity * 0.8  # 80% for same region
    cross_region_target = total_collection_capacity * 0.2  # 20% for cross region
    
    prioritized_generators = []
    
    # Phase 1: Select same-region generators for 80% of capacity
    if same_region_generators and same_region_target > 0:
        # Sort by storage volume (highest first) for efficiency
        same_region_sorted = sorted(
            same_region_generators, 
            key=lambda g: g.current_storage, 
            reverse=True
        )
        
        # Select generators until we reach 80% capacity target
        selected_same_region = []
        accumulated_volume = 0
        
        for generator in same_region_sorted:
            if accumulated_volume >= same_region_target:
                break
                
            # Calculate how much we can collect from this generator
            collectible = min(
                generator.current_storage,
                same_region_target - accumulated_volume
            )
            
            if collectible > 0:
                selected_same_region.append(generator)
                accumulated_volume += collectible
        
        prioritized_generators.extend(selected_same_region)
        
        print(f"[VOLUME ALLOCATION] {collector.name}: Same region target {same_region_target:.1f}m³, "
              f"selected {len(selected_same_region)} generators "
              f"({accumulated_volume:.1f}m³ potential)")
    
    # Phase 2: Select cross-region generators for 20% of capacity
    if other_region_generators and cross_region_target > 0:
        # Find the closest region with available generators
        closest_regions = get_closest_regions(collector.region_type, n=3)  # Get top 3 closest
        
        for region_type, distance in closest_regions:
            region_generators = [
                g for g in other_region_generators 
                if g.region_type == region_type
            ]
            
            if region_generators:
                # Sort by storage volume (highest first)
                region_sorted = sorted(
                    region_generators,
                    key=lambda g: g.current_storage,
                    reverse=True
                )
                
                # Select generators until we reach 20% capacity target
                selected_cross_region = []
                accumulated_volume = 0
                
                for generator in region_sorted:
                    if accumulated_volume >= cross_region_target:
                        break
                        
                    collectible = min(
                        generator.current_storage,
                        cross_region_target - accumulated_volume
                    )
                    
                    if collectible > 0:
                        selected_cross_region.append(generator)
                        accumulated_volume += collectible
                
                if selected_cross_region:
                    prioritized_generators.extend(selected_cross_region)
                    
                    print(f"[VOLUME ALLOCATION] {collector.name}: Cross region target {cross_region_target:.1f}m³, "
                          f"selected {len(selected_cross_region)} generators from {region_type.value} "
                          f"({accumulated_volume:.1f}m³ potential, {distance:.1f}km)")
                    break  # Only use the closest region
    
    return prioritized_generators


def get_volume_weighted_generators(collector, target_same_region_ratio: float = 0.8) -> List:
    """
    Alternative implementation with configurable volume ratios
    
    Args:
        collector: The collector instance
        target_same_region_ratio: Ratio of capacity for same region (default 0.8 = 80%)
        
    Returns:
        List of generators selected based on volume allocation strategy
    """
    
    state = SimulationState.get_instance()
    
    generators_with_waste = [
        g for g in state.generators
        if g.current_storage > 0
    ]
    
    if not generators_with_waste:
        return []
    
    # Calculate capacity allocations
    total_capacity = collector.collection_capacity * collector.efficiency
    same_region_capacity = total_capacity * target_same_region_ratio
    cross_region_capacity = total_capacity * (1 - target_same_region_ratio)
    
    result = []
    
    # Group generators by region
    generators_by_region = {}
    for gen in generators_with_waste:
        if gen.region_type not in generators_by_region:
            generators_by_region[gen.region_type] = []
        generators_by_region[gen.region_type].append(gen)
    
    # Sort each region's generators by storage volume (descending)
    for region_type in generators_by_region:
        generators_by_region[region_type].sort(
            key=lambda g: g.current_storage, reverse=True
        )
    
    # Phase 1: Allocate same-region capacity
    same_region_gens = generators_by_region.get(collector.region_type, [])
    if same_region_gens and same_region_capacity > 0:
        allocated_volume = 0
        
        for gen in same_region_gens:
            if allocated_volume >= same_region_capacity:
                break
                
            # Add generator if it contributes to our capacity target
            potential_collection = min(gen.current_storage, same_region_capacity - allocated_volume)
            if potential_collection > 0:
                result.append(gen)
                allocated_volume += potential_collection
        
        print(f"[VOLUME SPLIT] {collector.name}: Same region allocation {allocated_volume:.1f}m³ "
              f"from {len([g for g in result if g.region_type == collector.region_type])} generators")
    
    # Phase 2: Allocate cross-region capacity to closest region
    if cross_region_capacity > 0:
        closest_regions = get_closest_regions(collector.region_type, n=5)
        
        for region_type, distance in closest_regions:
            if region_type in generators_by_region:
                cross_region_gens = generators_by_region[region_type]
                allocated_volume = 0
                cross_region_count = 0
                
                for gen in cross_region_gens:
                    if allocated_volume >= cross_region_capacity:
                        break
                        
                    potential_collection = min(gen.current_storage, cross_region_capacity - allocated_volume)
                    if potential_collection > 0:
                        result.append(gen)
                        allocated_volume += potential_collection
                        cross_region_count += 1
                
                if cross_region_count > 0:
                    print(f"[VOLUME SPLIT] {collector.name}: Cross region allocation {allocated_volume:.1f}m³ "
                          f"from {cross_region_count} generators in {region_type.value} ({distance:.1f}km)")
                    break  # Only use closest available region
    
    return result

