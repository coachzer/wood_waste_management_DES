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

    def request_collection(self, required_waste: float, input_waste_types: set) -> CollectionResult:
        """Request waste collection from available collectors"""
        if required_waste <= 0:
            return CollectionResult(total_collected=0, waste_by_type={})

        print(f"\n{self.env.now}: Requesting collection of {required_waste:.12f} m³")

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

        if total_collected > 0:
            print(f"Total waste collected: {total_collected:.12f} m³")

        return CollectionResult(
            total_collected=total_collected,
            waste_by_type=total_by_type
        )

    def _get_collectors_with_waste(self, state: SimulationState) -> List[CollectorCompany]:
        """Get collectors that have waste stored"""
        return [
            c for c in state.collectors
            if c.region_type == self.region_type
            and c.availability
            and sum(c.collection_center.current_storage.values()) > 0
        ]

    def _get_available_collectors(self, state: SimulationState) -> List[CollectorCompany]:
        """Get all available collectors in the region"""
        return [
            c for c in state.collectors
            if c.region_type == self.region_type and c.availability
        ]

    def _transfer_stored_waste(
        self, 
        collectors: List[CollectorCompany],
        required_waste: float,
        total_by_type: Dict[WasteType, float],
        input_waste_types: set
    ) -> float:
        """Transfer waste from collectors' storage"""
        total_collected = 0

        for collector in collectors:
            if total_collected >= required_waste:
                break

            remaining_need = required_waste - total_collected
            for waste_type in input_waste_types:
                if waste_type in collector.collection_center.current_storage:
                    available = collector.collection_center.current_storage[waste_type]
                    if available > 0:
                        transfer_amount = min(available, remaining_need)
                        collector.collection_center.current_storage[waste_type] -= transfer_amount
                        total_by_type[waste_type] += transfer_amount
                        total_collected += transfer_amount
                        print(
                            f"Transferred {transfer_amount:.12f} m³ of {waste_type} from {collector.name}'s storage"
                        )

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

        for collector in collectors:
            remaining_need = required_waste - total_collected
            if remaining_need <= 0:
                break

            collected_amounts = collector.collect_waste_for_demand(remaining_need)

            for waste_type, amount in collected_amounts.items():
                if amount > 0:
                    total_by_type[waste_type] += amount
                    total_collected += amount
                    print(
                        f"Collected {amount:.12f} m³ of {waste_type.value} from {collector.name}"
                    )

        return total_collected
