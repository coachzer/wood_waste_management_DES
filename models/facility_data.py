from typing import Dict, Optional
import json
from pathlib import Path
from .enums import RegionType
from .entities import RegionalFacilities
from .products import ProductDataManager


class FacilityDataManager:
    """Manager class for loading and accessing facility data"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.regions: Dict[RegionType, RegionalFacilities] = {}
        self.demand: Dict[str, float] = {}
        self.product_manager = ProductDataManager()

    def load_data(self):
        """Load all facility and demand data"""
        self._load_regions()
        self._load_demand()

    def _load_regions(self):
        """Load facility data for all regions"""
        regions_dir = self.data_dir / "regions"
        for region in RegionType:
            file_path = regions_dir / f"{region.value}.json"
            print(f"DEBUG: Loading region {region.value} from {file_path}")
            if file_path.exists():
                with open(file_path, "r") as f:
                    data = json.load(f)
                    print(f"DEBUG: Loaded data keys for {region.value}: {list(data.keys()) if data else 'None'}")
                    if data:
                        self.regions[region] = RegionalFacilities.from_dict(data)

    def _load_demand(self):
        """Load national demand data"""
        demand_path = self.data_dir / "demand.json"
        if demand_path.exists():
            with open(demand_path, "r") as f:
                data = json.load(f)
                self.demand = data["national_demand"]

    def get_region_facilities(self, region: RegionType) -> Optional[RegionalFacilities]:
        """Get facilities for a specific region"""
        return self.regions.get(region)

    def get_demand(self, product_type: str) -> float:
        """Get national demand for a specific product type"""
        return self.demand.get(product_type, 0)
    
    # Delegate product-related methods to ProductDataManager
    def get_product_specification(self, product_type: str):
        return self.product_manager.get_product_specification(product_type)
    
    def get_product_recipe(self, product_type: str):
        return self.product_manager.get_product_recipe(product_type)
    
    def get_waste_mapping(self, ewc_code: str):
        return self.product_manager.get_waste_mapping(ewc_code)
    
    def can_produce_from_waste(self, product_type: str, ewc_codes):
        return self.product_manager.can_produce_from_waste(product_type, ewc_codes)
    
    def get_products_by_biogenic_priority(self):
        return self.product_manager.get_products_by_biogenic_priority()
