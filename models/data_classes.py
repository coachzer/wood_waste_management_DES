from dataclasses import dataclass
from typing import Dict, Optional, List
from .enums import WasteType


@dataclass
class WasteStream:
    """Data class to represent a waste stream"""

    waste_type: WasteType
    volume: float
    density: float
    moisture_content: float

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
