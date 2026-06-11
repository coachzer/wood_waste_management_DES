from typing import Dict, List, Optional
from dataclasses import dataclass
from .data_classes import FailureConfig, OperationalEntity


@dataclass
class Generator(OperationalEntity):
    """Waste generator entity"""
    id: str
    waste_generation_rates: Dict[str, float]  # EWC code -> tonne/day
    generation_frequency: float
    waste_storage_capacity: float
    environmental_impact: float
    efficiency: float
    initial_stock: Optional[Dict[str, float]] = None

    def __init__(self, 
                 id: str,
                 waste_generation_rates: Dict[str, float],
                 generation_frequency: float,
                 waste_storage_capacity: float,
                 environmental_impact: float,
                 efficiency: float,
                 initial_stock: Optional[Dict[str, float]] = None,
                 failure_config: Optional[FailureConfig] = None):  
        super().__init__(failure_config=failure_config)
        self.id = id
        self.waste_generation_rates = waste_generation_rates
        self.generation_frequency = generation_frequency
        self.waste_storage_capacity = waste_storage_capacity
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.initial_stock = initial_stock


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

    def __init__(self, 
                 id: str, 
                 waste_types: List[str], 
                 collection_capacity: float,
                 collection_frequency: float, 
                 transport_cost: float,
                 environmental_impact: float, 
                 efficiency: float,
                 availability: bool,
                 failure_config: Optional[FailureConfig] = None):
        super().__init__(failure_config=failure_config)
        self.id = id
        self.waste_types = waste_types
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability


@dataclass
class Processor(OperationalEntity):
    """Treatment/processing facility"""
    id: str
    input_types: List[str]  # EWC codes that can be processed
    output_types: List[str]  # Products that can be produced
    processing_time: float
    waste_storage_capacity: float
    energy_consumption: float = 1.0
    environmental_impact: float = 1.0
    conversion_rate: float = 1.0
    operational_costs: float = 1.0

    def __init__(self,
                 id: str,
                 input_types: List[str],
                 output_types: List[str],
                 processing_time: float,
                 waste_storage_capacity: float,
                 energy_consumption: float = 1.0,
                 environmental_impact: float = 1.0,
                 conversion_rate: float = 1.0,
                 operational_costs: float = 1.0,
                 failure_config: Optional[FailureConfig] = None):
        super().__init__(failure_config=failure_config)
        self.id = id
        self.input_types = input_types
        self.output_types = output_types
        self.processing_time = processing_time
        self.waste_storage_capacity = waste_storage_capacity
        self.energy_consumption = energy_consumption
        self.environmental_impact = environmental_impact
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs

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
            processors=[Processor(**p) for p in data["processors"]]
        )
