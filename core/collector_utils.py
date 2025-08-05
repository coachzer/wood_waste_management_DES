from typing import List, Dict, Optional
from models.distances import get_closest_regions
from models.enums import InventoryPolicy, StockStrategy, WasteType
from models.state import SimulationState

def handle_completed_transport(transport: Dict, current_time: float) -> None:
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
        # print(
        #     f"{current_time}: Added {transport['volume']:.8f} m³ to "
        #     f"{target_collector.name}'s collection center"
        # )

def check_completed_transports(active_transports: List[Dict], current_time: float) -> List[Dict]:
    """Identify completed transports and update vehicle status"""
    completed = []
    for transport in active_transports:
        if current_time >= transport["arrival_time"]:
            vehicle = transport["vehicle"]
            vehicle.in_transit = False
            vehicle.current_load = 0
            vehicle.current_region = vehicle.destination
            vehicle.destination = None
            vehicle.estimated_arrival = None
            completed.append(transport)
    return completed

def normalize_waste_type(waste_type_input) -> Optional[WasteType]:
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
            
        if (waste_type_enum in collector_waste_types or 
            waste_type_enum.value in collector_waste_types):
            active_streams[waste_type_enum] = stream
    
    return active_streams

def get_adaptive_threshold(strategy: StockStrategy, base_time: float) -> float:
    """Get adaptive threshold that increases over time for ON_DEMAND"""
    match strategy:
        case StockStrategy.ON_DEMAND:
            # Gradually increase threshold over time to trigger more collections
            time_factor = min(0.3, base_time * 0.001)  # Caps at 30%
            return 0.10 + time_factor  # Start at 10%, grow to 40%
        case StockStrategy.REORDER_50:
            return 0.50
        case StockStrategy.REORDER_90:
            return 0.90
        case _:
            raise ValueError(f"Unknown StockStrategy: {strategy}")

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
    """Calculate efficiency for PUSH policies with smooth curves"""
    
    utilization = max(0.0, min(1.0, utilization))
    
    match strategy:
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
                underutilization_penalty = (0.3 - utilization) * 0.2  # Up to 6% penalty
                return base * (1.0 - underutilization_penalty)
            else:
                # Penalty for overutilization
                overutilization_penalty = (utilization - 0.7) * 0.15  # Up to 4.5% penalty
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
            raise ValueError(f"Unknown StockStrategy: {strategy}")

def _calculate_pull_efficiency(strategy: StockStrategy, utilization: float, 
                              signals: int, base: float) -> float:
    """Calculate efficiency for PULL policies with signal responsiveness"""
    
    # Clamp utilization and signals to reasonable ranges
    utilization = max(0.0, min(1.0, utilization))
    signals = max(0, signals)
    
    match strategy:
        case StockStrategy.ON_DEMAND:
            if signals == 0:
                # No demand - minor efficiency loss (idle resources)
                return base * 0.98
            else:
                # More signals = better utilization of ON_DEMAND capabilities
                signal_boost = min(0.15, signals * 0.02)  # Up to 15% efficiency gain
                
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

def get_prioritized_generators(collector) -> List:
    """Get generators with 80% volume allocation to same region, 20% to next closest region"""
    
    state = SimulationState.get_instance()
    
    generators_with_waste = [
        g for g in state.generators
        if g.current_storage > 0
    ]
    
    if not generators_with_waste:
        return []
    
    total_collection_capacity = collector.collection_capacity * collector.efficiency
    
    same_region_generators = [
        g for g in generators_with_waste 
        if g.region_type == collector.region_type
    ]
    
    other_region_generators = [
        g for g in generators_with_waste 
        if g.region_type != collector.region_type
    ]
    
    same_region_target = total_collection_capacity * 0.8  # 80% for same region
    cross_region_target = total_collection_capacity * 0.2  # 20% for cross region
    
    prioritized_generators = []
    
    if same_region_generators and same_region_target > 0:
        same_region_sorted = sorted(
            same_region_generators, 
            key=lambda g: g.current_storage, 
            reverse=True
        )
    
        selected_same_region = []
        accumulated_volume = 0
        
        for generator in same_region_sorted:
            if accumulated_volume >= same_region_target:
                break
                
            collectible = min(
                generator.current_storage,
                same_region_target - accumulated_volume
            )
            
            if collectible > 0:
                selected_same_region.append(generator)
                accumulated_volume += collectible
        
        prioritized_generators.extend(selected_same_region)
    
    if other_region_generators and cross_region_target > 0:
        closest_regions = get_closest_regions(collector.region_type, n=3)  # Get top 3 closest
        
        for region_type, distance in closest_regions:
            region_generators = [
                g for g in other_region_generators 
                if g.region_type == region_type
            ]
            
            if region_generators:
                region_sorted = sorted(
                    region_generators,
                    key=lambda g: g.current_storage,
                    reverse=True
                )
                
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
                    break  
    
    return prioritized_generators
