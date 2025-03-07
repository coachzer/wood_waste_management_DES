from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from .enums import WasteType, RegionType

@dataclass
class CollectionResult:
    """Data class to represent results from a collection request"""
    total_collected: float
    waste_by_type: Dict[WasteType, float]


@dataclass
class WasteStream:
    """Data class to represent a waste stream"""

    waste_type: WasteType
    volume: float

    @property
    def mass(self) -> float:
        return self.volume * self.density


@dataclass
class WasteTransformation:
    """Data class to represent a waste transformation process"""

    input_type: WasteType
    output_type: WasteType
    conversion_efficiency: float  # Percentage of input mass converted to output
    energy_required: float  # Energy required per unit mass (kWh/kg)


@dataclass
class Vehicle:
    """Data class to represent a transport vehicle"""

    id: str
    capacity: float
    current_region: RegionType
    in_transit: bool = False
    current_load: float = 0.0
    destination: Optional[RegionType] = None
    estimated_arrival: Optional[float] = None


@dataclass
class CollectionCenter:
    """Data class to represent a waste collection center"""

    region: RegionType
    storage_capacity: float
    current_storage: Dict[WasteType, float]
    coordinates: Tuple[float, float]
