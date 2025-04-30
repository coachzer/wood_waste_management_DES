from typing import Dict, List, Optional
from dataclasses import dataclass
import json
from pathlib import Path
from .enums import RegionType


@dataclass
class Generator:
    id: str
    waste_generation_rates: Dict[str, float]
    generation_frequency: float
    storage_capacity: float
    priority_level: int
    environmental_impact: float
    initial_stock: Optional[Dict[str, float]] = None


@dataclass
class Collector:
    id: str
    waste_types: List[str]
    collection_capacity: float
    collection_frequency: float
    transport_cost: float
    environmental_impact: float
    efficiency: float
    availability: bool
    strategy: str


@dataclass
class Processor:
    id: str
    input_types: List[str]
    output_types: List[str]
    processing_capacity: float
    processing_time: float
    storage_capacity: float
    energy_consumption: float
    environmental_impact: float
    conversion_rate: float
    operational_costs: float


@dataclass
class RegionalFacilities:
    generators: List[Generator]
    collectors: List[Collector]
    processors: List[Processor]

    @classmethod
    def from_dict(cls, data: Dict) -> "RegionalFacilities":
        return cls(
            generators=[Generator(**g) for g in data["generators"]],
            collectors=[Collector(**c) for c in data["collectors"]],
            processors=[Processor(**p) for p in data["processors"]],
        )


class FacilityDataManager:
    """Manager class for loading and accessing facility data"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.regions: Dict[RegionType, RegionalFacilities] = {}
        self.demand: Dict[str, float] = {}
        self.period_info: Dict = {}

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
                    if data:  # Only process non-empty JSON files
                        self.regions[region] = RegionalFacilities.from_dict(data)

    def _load_demand(self):
        """Load national demand data"""
        demand_path = self.data_dir / "demand.json"
        if demand_path.exists():
            with open(demand_path, "r") as f:
                data = json.load(f)
                self.demand = data["national_demand"]
                self.period_info = data.get("period", {})

    def get_region_facilities(self, region: RegionType) -> Optional[RegionalFacilities]:
        """Get facilities for a specific region"""
        return self.regions.get(region)

    def get_all_generators(self) -> List[Generator]:
        """Get all generators across all regions"""
        return [gen for region in self.regions.values() for gen in region.generators]

    def get_all_collectors(self) -> List[Collector]:
        """Get all collectors across all regions"""
        return [col for region in self.regions.values() for col in region.collectors]

    def get_all_processors(self) -> List[Processor]:
        """Get all processors across all regions"""
        return [proc for region in self.regions.values() for proc in region.processors]

    def get_total_processing_capacity(self, output_type: str) -> float:
        """Get total processing capacity for a specific output type across all regions"""
        return sum(
            proc.processing_capacity
            for region in self.regions.values()
            for proc in region.processors
            if output_type in proc.output_types
        )

    def get_demand(self, product_type: str) -> float:
        """Get national demand for a specific product type"""
        return self.demand.get(product_type, 0)
