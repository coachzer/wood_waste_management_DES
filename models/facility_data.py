from typing import Dict, Optional
import json
from pathlib import Path
from .enums import RegionType
from .entities import RegionalFacilities


class FacilityDataManager:
    """Manager class for loading and accessing facility data"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.regions: Dict[RegionType, RegionalFacilities] = {}
        self.demand: Dict[str, float] = {}

    def load_data(self):
        """Load all facility and demand data"""
        self._load_regions()
        self._load_demand()

    def _load_regions(self):
        """Load facility data for all regions"""
        regions_dir = self.data_dir / "regions"
        for region in RegionType:
            file_path = regions_dir / f"{region.value}.json"
            if file_path.exists():
                with open(file_path, "r") as f:
                    data = json.load(f)
                    if data:
                        self.regions[region] = RegionalFacilities.from_dict(data)

    def _load_demand(self):
        """Load national demand data.

        A missing file raises: demand drives the ABC priority weights, so a
        moved or renamed file must fail loudly instead of degrading every run.
        """
        with open(self.data_dir / "demand.json", "r") as f:
            self.demand = json.load(f)["national_demand"]

    def get_region_facilities(self, region: RegionType) -> Optional[RegionalFacilities]:
        """Get facilities for a specific region"""
        return self.regions.get(region)

