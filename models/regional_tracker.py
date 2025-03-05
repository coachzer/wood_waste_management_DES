from typing import Dict, Union
from .enums import RegionType, WasteType
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class RegionalWasteInventory:
    """Tracks waste amounts for each type in a region"""

    inventory: Dict[WasteType, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def add_waste(self, waste_type: WasteType, amount: float) -> None:
        """Add waste of specific type to the region's inventory"""
        self.inventory[waste_type] += amount

    def remove_waste(self, waste_type: WasteType, amount: float) -> float:
        """
        Remove waste of specific type from the region's inventory.
        Returns actual amount removed (may be less if not enough available).
        """
        available = self.inventory[waste_type]
        removal = min(available, amount)
        self.inventory[waste_type] -= removal
        return removal

    def get_amount(self, waste_type: WasteType) -> float:
        """Get current amount of specific waste type"""
        return self.inventory[waste_type]


class RegionalWasteTracker:
    """Tracks waste inventory across all regions"""

    def __init__(self):
        self.regional_inventory: Dict[RegionType, RegionalWasteInventory] = {
            region: RegionalWasteInventory() for region in RegionType
        }

    def _get_region_type(self, region: Union[str, RegionType]) -> RegionType:
        """Convert region string or enum to RegionType"""
        if isinstance(region, RegionType):
            return region
        try:
            # First try to match by value (e.g., "pomurska")
            for region_type in RegionType:
                if region_type.value == region.lower():
                    return region_type
            # If no match found by value, try by enum name (e.g., "POMURSKA")
            return RegionType[region.upper()]
        except (KeyError, AttributeError):
            raise KeyError(
                f"Invalid region: {region}. Must be one of {[r.value for r in RegionType]}"
            )

    def add_waste(
        self, region: Union[str, RegionType], waste_type: WasteType, amount: float
    ) -> None:
        """Track waste addition in a specific region"""
        region_type = self._get_region_type(region)
        self.regional_inventory[region_type].add_waste(waste_type, amount)

    def remove_waste(
        self, region: Union[str, RegionType], waste_type: WasteType, amount: float
    ) -> float:
        """Track waste removal from a specific region"""
        region_type = self._get_region_type(region)
        return self.regional_inventory[region_type].remove_waste(waste_type, amount)

    def get_regional_stats(
        self, region: Union[str, RegionType]
    ) -> Dict[WasteType, float]:
        """Get current waste amounts by type for a specific region"""
        region_type = self._get_region_type(region)
        return dict(self.regional_inventory[region_type].inventory)

    def get_waste_type_stats(self, waste_type: WasteType) -> Dict[RegionType, float]:
        """Get distribution of a specific waste type across all regions"""
        return {
            region: self.regional_inventory[region].get_amount(waste_type)
            for region in RegionType
        }
