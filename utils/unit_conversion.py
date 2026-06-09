from typing import Dict, Optional
from config.constants import KILOGRAMS_PER_TONNE, WASTE_DENSITIES
from models.enums import WasteType

def _tonnes_to_cubic_meters(tonnes: float, waste_type: WasteType) -> float:
    """
    Convert tonnes to cubic meters for a specific waste type
    """
    if waste_type not in WASTE_DENSITIES:
        raise ValueError(f"Unknown waste type {waste_type}, cannot determine density for conversion.")
    else:
        density_kg_m3 = WASTE_DENSITIES[waste_type]

    kg = tonnes * KILOGRAMS_PER_TONNE
    cubic_meters = kg / density_kg_m3

    return cubic_meters

def _create_waste_type_mapping(generation_rates_tonnes: Dict[str, float]) -> Dict[str, WasteType]:
    """Helper to create waste type mapping from EWC codes."""
    waste_type_mapping = {}
    for ewc_code in generation_rates_tonnes.keys():
        try:
            normalized_code = ewc_code.replace(" ", "_").upper()
            # Find the corresponding WasteType enum
            matching_waste_type = next(
                (wt for wt in WasteType if wt.name.endswith(normalized_code)),
                None
            )
            if matching_waste_type:
                waste_type_mapping[ewc_code] = matching_waste_type
        except Exception as e:
            raise ValueError(f"Could not map EWC code {ewc_code}: {e}")
    return waste_type_mapping

def convert_generation_rates_to_volume(
    generation_rates_tonnes: Dict[str, float], 
    waste_type_mapping: Optional[Dict[str, WasteType]] = None
) -> Dict[WasteType, float]:
    """
    Convert waste generation rates from tonnes/day to m³/day
    """
    if waste_type_mapping is None:
        waste_type_mapping = _create_waste_type_mapping(generation_rates_tonnes)
    
    volume_rates = {}
    
    for ewc_code, tonnes_per_day in generation_rates_tonnes.items():
        if ewc_code in waste_type_mapping:
            waste_type = waste_type_mapping[ewc_code]
            volume_per_day = _tonnes_to_cubic_meters(tonnes_per_day, waste_type)
            volume_rates[waste_type] = volume_per_day
        else:
            print(f"Warning: EWC code {ewc_code} not found in waste type mapping")
    
    return volume_rates