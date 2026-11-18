from typing import Dict, List, Optional
from dataclasses import dataclass
from .data_classes import FailureConfig, OperationalEntity
from .enums import WasteType, normalize_waste_type


@dataclass
class Generator(OperationalEntity):
    """Waste generator entity"""
    id: str
    waste_generation_rates: Dict[WasteType, float]
    generation_frequency: float
    waste_storage_capacity: float
    efficiency: float
    initial_stock: Optional[Dict[WasteType, float]] = None

    def __init__(self,
                 id: str,
                 waste_generation_rates: Dict[WasteType, float],
                 generation_frequency: float,
                 waste_storage_capacity: float,
                 efficiency: float,
                 initial_stock: Optional[Dict[WasteType, float]] = None,
                 failure_config: Optional[FailureConfig] = None):
        super().__init__(failure_config=failure_config)
        self.id = id
        self.waste_generation_rates = waste_generation_rates
        self.generation_frequency = generation_frequency
        self.waste_storage_capacity = waste_storage_capacity
        self.efficiency = efficiency
        self.initial_stock = initial_stock


@dataclass
class Collector(OperationalEntity):
    """Waste collector entity"""
    id: str
    waste_types: List[WasteType]
    collection_capacity: float
    collection_frequency: float
    transport_cost: float
    efficiency: float
    availability: bool

    def __init__(self,
                 id: str,
                 waste_types: List[WasteType],
                 collection_capacity: float,
                 collection_frequency: float,
                 transport_cost: float,
                 efficiency: float,
                 availability: bool,
                 failure_config: Optional[FailureConfig] = None):
        super().__init__(failure_config=failure_config)
        self.id = id
        self.waste_types = waste_types
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.efficiency = efficiency
        self.availability = availability


@dataclass
class Processor(OperationalEntity):
    """Treatment/processing facility"""
    id: str
    input_types: List[WasteType]
    output_types: List[str]
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
            generators=[Generator(**_with_waste_type_keys(g)) for g in data["generators"]],
            collectors=[Collector(**_with_waste_type_lists(c, "waste_types")) for c in data["collectors"]],
            processors=[Processor(**_with_waste_type_lists(p, "input_types")) for p in data["processors"]]
        )


def _parse_waste_type(code):
    waste_type = normalize_waste_type(code)
    if waste_type is None:
        print(f"Warning: EWC code {code} not found in waste type mapping")
    return waste_type


def _waste_types_in(codes) -> List[WasteType]:
    return [waste_type for waste_type in map(_parse_waste_type, codes) if waste_type is not None]


def _rates_by_waste_type(rates_by_code: Dict) -> Dict[WasteType, float]:
    rates_by_waste_type = {}
    for code, rate in rates_by_code.items():
        waste_type = _parse_waste_type(code)
        if waste_type is not None:
            rates_by_waste_type[waste_type] = rate
    return rates_by_waste_type


def _with_waste_type_keys(generator_data: Dict) -> Dict:
    parsed = dict(generator_data)
    for field_name in ("waste_generation_rates", "initial_stock"):
        if parsed.get(field_name):
            parsed[field_name] = _rates_by_waste_type(parsed[field_name])
    return parsed


def _with_waste_type_lists(facility_data: Dict, field_name: str) -> Dict:
    parsed = dict(facility_data)
    parsed[field_name] = _waste_types_in(parsed.get(field_name, []))
    return parsed
