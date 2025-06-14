from dataclasses import dataclass
from typing import Dict
import json
from models.enums import WasteType

@dataclass
class RateConfig:
    """Configuration for a rate with uncertainty"""
    mean: float
    std: float

    def validate(self) -> bool:
        """Validate rate parameters"""
        if self.mean < 0:
            return False
        if self.std < 0:
            return False
        return True

@dataclass
class CollectionConfig:
    """Configuration for collection parameters"""
    efficiency: RateConfig
    frequency: float
    capacity: float

    def validate(self) -> bool:
        """Validate collection parameters"""
        if not self.efficiency.validate():
            return False
        if self.frequency <= 0:
            return False
        if self.capacity <= 0:
            return False
        return True

@dataclass
class RegionConfig:
    """Configuration for a single region"""
    generation_rates: Dict[WasteType, RateConfig]
    collection: CollectionConfig
    storage_capacity: float

    def validate(self) -> bool:
        """Validate region configuration"""
        for rate in self.generation_rates.values():
            if not rate.validate():
                return False
        if not self.collection.validate():
            return False
        if self.storage_capacity <= 0:
            return False
        return True

@dataclass
class UncertaintyParams:
    """Global uncertainty parameters"""
    equipment_failure_probability: float
    min_failure_duration: float
    max_failure_duration: float

    def validate(self) -> bool:
        """Validate uncertainty parameters"""
        if not 0 <= self.equipment_failure_probability <= 1:
            return False
        if self.min_failure_duration <= 0:
            return False
        if self.max_failure_duration < self.min_failure_duration:
            return False
        return True

@dataclass
class ScenarioConfig:
    """Complete scenario configuration"""
    name: str
    regions: Dict[str, RegionConfig]
    uncertainty_params: UncertaintyParams
    product_conversions: Dict[str, Dict[str, float]]

    def validate(self) -> bool:
        """Validate complete scenario configuration"""
        if not self.name:
            return False
        for region in self.regions.values():
            if not region.validate():
                return False
        if not self.uncertainty_params.validate():
            return False
        # Product conversions validation could be added here
        return True

class ScenarioBuilder:
    """Builder for scenario configurations"""
    def __init__(self):
        self._reset()

    def _reset(self):
        """Reset builder state"""
        self.name = ""
        self.regions = {}
        self.uncertainty_params = None
        self.product_conversions = {}

    def load_from_json(self, json_path: str) -> 'ScenarioBuilder':
        """Load configuration from JSON file"""
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        self.name = data.get('scenario_name', '')
        
        # Parse regions
        for region_name, region_data in data.get('regions', {}).items():
            generation_rates = {}
            for waste_type, rate_data in region_data.get('generation_rates', {}).items():
                generation_rates[WasteType[waste_type.upper()]] = RateConfig(
                    mean=rate_data['mean'],
                    std=rate_data['std']
                )
            
            collection_data = region_data.get('collection', {})
            collection = CollectionConfig(
                efficiency=RateConfig(
                    mean=collection_data['efficiency']['mean'],
                    std=collection_data['efficiency']['std']
                ),
                frequency=collection_data.get('frequency', 24.0),
                capacity=collection_data.get('capacity', 1000.0)
            )
            
            self.regions[region_name] = RegionConfig(
                generation_rates=generation_rates,
                collection=collection,
                storage_capacity=region_data.get('storage_capacity', 1000.0)
            )
            
        # Parse uncertainty parameters
        uncertainty_data = data.get('uncertainty_parameters', {})
        self.uncertainty_params = UncertaintyParams(
            equipment_failure_probability=uncertainty_data.get('equipment_failure', {}).get('probability', 0.001),
            min_failure_duration=uncertainty_data.get('equipment_failure', {}).get('min_duration', 12.0),
            max_failure_duration=uncertainty_data.get('equipment_failure', {}).get('max_duration', 24.0)
        )
        
        # Parse product conversions
        self.product_conversions = data.get('product_conversions', {})
        
        return self

    def build(self) -> ScenarioConfig:
        """Build and validate scenario configuration"""
        config = ScenarioConfig(
            name=self.name,
            regions=self.regions,
            uncertainty_params=self.uncertainty_params,
            product_conversions=self.product_conversions
        )
        
        if not config.validate():
            raise ValueError("Invalid scenario configuration")
            
        return config
