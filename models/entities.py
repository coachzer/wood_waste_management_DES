from typing import Dict, List, Optional
from dataclasses import dataclass
from .enums import RegionType, EntityStatus, WasteType
from .data_classes import OperationalEntity


@dataclass
class Generator:
    """Waste generator entity"""
    id: str
    waste_generation_rates: Dict[str, float]  # EWC code -> kg/day
    generation_frequency: float
    storage_capacity: float
    environmental_impact: float
    initial_stock: Optional[Dict[str, float]] = None


@dataclass
class Collector(OperationalEntity):
    """Waste collector entity"""
    id: str
    waste_types: List[str]  # EWC codes
    collection_capacity: float
    collection_frequency: float
    transport_cost: float
    environmental_impact: float
    efficiency: float
    availability: bool
    strategy: str

    def __init__(self, id: str, waste_types: List[str], collection_capacity: float,
                 collection_frequency: float, transport_cost: float,
                 environmental_impact: float, efficiency: float,
                 availability: bool, strategy: str):
        super().__init__()
        self.id = id
        self.waste_types = waste_types
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        self.strategy = strategy
        self.downtime_duration = 12.0  # Collectors repair faster


@dataclass
class Processor(OperationalEntity):
    """Treatment/processing facility"""
    id: str
    input_types: List[str]  # EWC codes that can be processed
    output_types: List[str]  # Products that can be produced
    processing_capacity: float
    processing_time: float
    storage_capacity: float
    product_storage_capacity: float = 10000.0
    energy_consumption: float = 1.0
    environmental_impact: float = 1.0
    conversion_rate: float = 1.0
    operational_costs: float = 1.0

    def __init__(self, id: str, input_types: List[str], output_types: List[str],
                 processing_capacity: float, processing_time: float,
                 storage_capacity: float, product_storage_capacity: float = 10000.0,
                 energy_consumption: float = 1.0, environmental_impact: float = 1.0,
                 conversion_rate: float = 1.0, operational_costs: float = 1.0):
        super().__init__()
        self.id = id
        self.input_types = input_types
        self.output_types = output_types
        self.processing_capacity = processing_capacity
        self.processing_time = processing_time
        self.storage_capacity = storage_capacity
        self.product_storage_capacity = product_storage_capacity
        self.energy_consumption = energy_consumption
        self.environmental_impact = environmental_impact
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs
        self.downtime_duration = 72.0  # Processors take longest to repair


@dataclass
class RegionalFacilities:
    """All facilities in a region"""
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
