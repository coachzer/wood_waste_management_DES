from typing import Dict, List, Optional
from models.enums import RegionType, WasteType
from models.state import SimulationState
from models.data_classes import CollectionResult
from core.collector import CollectorCompany

class CollectionCoordinator:
    """Coordinates waste collection between treatment facilities and collectors"""

    def __init__(self, env, region: str):
        self.env = env
        self.region = region
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None

    MIN_COLLECTION_VOLUME = 0.01  # Minimum volume threshold for collection

    def request_collection(self, required_waste: float, input_waste_types: set) -> CollectionResult:
        """Request waste collection from available collectors"""
        # Validate and adjust required waste amount
        if required_waste < self.MIN_COLLECTION_VOLUME:
            return CollectionResult(total_collected=0, waste_by_type={})

        # Round to prevent floating point precision issues
        required_waste = round(required_waste, 6)

        total_by_type = {waste_type: 0.0 for waste_type in WasteType}
        
        # Get collectors with stored waste and those that can collect more
        state = SimulationState.get_instance()
        collectors_with_stored_waste = self._get_collectors_with_waste(state)
        collectors_for_collection = self._get_available_collectors(state)

        # First use stored waste
        total_collected = self._transfer_stored_waste(
            collectors_with_stored_waste, 
            required_waste,
            total_by_type,
            input_waste_types
        )

        # Then request additional collection if needed
        total_collected = self._request_additional_collection(
            collectors_for_collection,
            required_waste,
            total_collected,
            total_by_type
        )

        return CollectionResult(
            total_collected=total_collected,
            waste_by_type=total_by_type
        )

    def _get_collectors_with_waste(self, state: SimulationState) -> List[CollectorCompany]:
        """Get collectors that have waste stored, prioritizing local region"""
        local_collectors = [
            c for c in state.collectors
            if c.region_type == self.region_type
            and c.availability
            and sum(c.collection_center.current_storage.values()) > 0
        ]
        
        if not local_collectors:
            # If no local collectors have waste, look in other regions
            return [
                c for c in state.collectors
                if c.availability
                and sum(c.collection_center.current_storage.values()) > 0
            ]
        return local_collectors

    def _get_available_collectors(self, state: SimulationState) -> List[CollectorCompany]:
        """Get all available collectors, prioritizing local region"""
        local_collectors = [
            c for c in state.collectors
            if c.region_type == self.region_type and c.availability
        ]
        
        if not local_collectors:
            # If no local collectors available, get collectors from other regions
            return [c for c in state.collectors if c.availability]
        return local_collectors

    def _transfer_stored_waste(
        self, 
        collectors: List[CollectorCompany],
        required_waste: float,
        total_by_type: Dict[WasteType, float],
        input_waste_types: set
    ) -> float:
        """Transfer waste from collectors' storage, prioritizing furniture materials"""
        total_collected = 0

        # Prioritize furniture materials first
        furniture_materials = {
            WasteType.CONSTRUCTION_WOOD,
            WasteType.WOOD_CUTTINGS,
            WasteType.WASTE_WOODEN_PACKAGING
        }
        
        # Split waste types into furniture and non-furniture
        priority_types = input_waste_types & furniture_materials
        other_types = input_waste_types - furniture_materials

        # Process priority types first, then other types
        for waste_type_group in [priority_types, other_types]:
            if not waste_type_group:  # Skip if no waste types in this group
                continue
            
            for collector in collectors:
                if total_collected >= required_waste: # Stop if enough waste collected
                    break

                remaining_need = required_waste - total_collected
                for waste_type in waste_type_group:
                    if waste_type in collector.collection_center.current_storage: # Check if collector has this waste type
                        available = collector.collection_center.current_storage[waste_type]
                        if available >= self.MIN_COLLECTION_VOLUME:
                            # For furniture materials, try to collect more to ensure enough supply
                            if waste_type in furniture_materials:
                                transfer_amount = max(
                                    self.MIN_COLLECTION_VOLUME,
                                    min(available, remaining_need * 1.2)  # 20% extra for furniture
                                )
                            else:
                                transfer_amount = max(
                                    self.MIN_COLLECTION_VOLUME,
                                    min(available, remaining_need)
                                )
                            
                            collector.collection_center.current_storage[waste_type] -= transfer_amount
                            total_by_type[waste_type] += transfer_amount
                            total_collected += transfer_amount

        return total_collected

    def _request_additional_collection(
        self,
        collectors: List[CollectorCompany],
        required_waste: float,
        total_collected: float,
        total_by_type: Dict[WasteType, float]
    ) -> float:
        """Request additional waste collection if needed"""
        if total_collected >= required_waste:
            return total_collected

        # Identify collectors in regions with furniture processors first
        furniture_regions = {RegionType.GORENJSKA, RegionType.GORISKA, RegionType.OSREDNJESLOVENSKA, RegionType.JUGOVZHODNA_SLOVENIJA}
        prioritized_collectors = self._filter_collectors_by_region(collectors, furniture_regions, include=True)
        other_collectors = self._filter_collectors_by_region(collectors, furniture_regions, include=False)
        
        # Process prioritized collectors first, then others
        for collector_group in [prioritized_collectors, other_collectors]:
            total_collected = self._collect_from_collector_group(
                collector_group, 
                required_waste, 
                total_collected, 
                total_by_type, 
                furniture_regions
            )
            if total_collected >= required_waste:
                break

        return total_collected
        
    def _filter_collectors_by_region(
        self, 
        collectors: List[CollectorCompany], 
        regions: set, 
        include: bool
    ) -> List[CollectorCompany]:
        """Filter collectors based on whether they're in specified regions"""
        if include:
            return [c for c in collectors if c.region_type in regions]
        else:
            return [c for c in collectors if c.region_type not in regions]
            
    def _collect_from_collector_group(
        self,
        collectors: List[CollectorCompany],
        required_waste: float,
        total_collected: float,
        total_by_type: Dict[WasteType, float],
        furniture_regions: set
    ) -> float:
        """Collect waste from a group of collectors"""
        for collector in collectors:
            remaining_need = required_waste - total_collected
            if remaining_need < self.MIN_COLLECTION_VOLUME:
                break
                
            # Adjust demand for furniture regions
            adjusted_need = remaining_need
            if collector.region_type in furniture_regions:
                adjusted_need *= 1.2  # Request 20% extra
                
            # Collect and process waste
            total_collected = self._process_collected_waste(
                collector, 
                adjusted_need, 
                total_collected, 
                total_by_type
            )
                
        return total_collected
        
    def _process_collected_waste(
        self,
        collector: CollectorCompany,
        demand: float,
        total_collected: float,
        total_by_type: Dict[WasteType, float]
    ) -> float:
        """Process waste collected from a single collector"""
        collected_amounts = collector.collect_waste_for_demand(demand)
        
        for waste_type, amount in collected_amounts.items():
            if amount > 0:
                total_by_type[waste_type] += amount
                total_collected += amount
                if amount >= self.MIN_COLLECTION_VOLUME:
                    print(
                        f"Collected {amount:.2f} m³ of {waste_type.value} from {collector.name}"
                    )
                    
        return total_collected
