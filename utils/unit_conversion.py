from typing import Dict
from config.constants import KILOGRAMS_PER_TONNE, WASTE_DENSITIES
from models.enums import WasteType

def _tonnes_to_cubic_meters(tonnes: float, waste_type: WasteType) -> float:
    """
    Convert tonnes to cubic meters for a specific waste type
    """
    if waste_type not in WASTE_DENSITIES:
        raise ValueError(f"Unknown waste type {waste_type}, cannot determine density for conversion.")
    density_kg_m3 = WASTE_DENSITIES[waste_type]

    kg = tonnes * KILOGRAMS_PER_TONNE
    cubic_meters = kg / density_kg_m3

    return cubic_meters

def convert_generation_rates_to_volume(generation_rates_tonnes: Dict[WasteType, float]) -> Dict[WasteType, float]:
    """Convert waste generation rates from tonnes/day to m3/day."""
    return {
        waste_type: _tonnes_to_cubic_meters(tonnes_per_day, waste_type)
        for waste_type, tonnes_per_day in generation_rates_tonnes.items()
    }
