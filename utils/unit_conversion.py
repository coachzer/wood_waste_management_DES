"""
Unit conversion utilities for waste management simulation

This module handles conversions between tonnes and cubic meters (m³) 
for different waste types based on their density characteristics.
"""

from typing import Dict, Optional
from models.enums import WasteType

# Standard waste densities in kg/m³ based on EWC codes and industry data
WASTE_DENSITIES = {
    WasteType.FORESTRY_WASTE_02_01_07: 350.0,
    WasteType.BARK_CORK_WASTE_03_01_01: 400.0,
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 200.0,
    WasteType.OTHER_WOOD_WASTE_03_01_99: 450.0,
    WasteType.BARK_WOOD_WASTE_03_03_01: 450.0,
    WasteType.PAPER_CARDBOARD_SORTING_WASTE_03_03_08: 600.0,
    WasteType.PAPER_PACKAGING_15_01_01: 600.0,
    WasteType.WOODEN_PACKAGING_15_01_03: 400.0,
    WasteType.CONSTRUCTION_WOOD_17_02_01: 500.0,
    WasteType.PAPER_CARDBOARD_19_12_01: 600.0,
    WasteType.WOOD_19_12_07: 400.0,
    WasteType.PAPER_CARDBOARD_20_01_01: 600.0,
    WasteType.NON_HAZARDOUS_WOOD_20_01_38: 450.0,
    WasteType.BULKY_WASTE_20_03_07: 300.0
}

def convert_ewc_dict_to_waste_type_dict(ewc_dict: Dict[str, str]) -> Dict[str, WasteType]:
    """
    Convert a dictionary of EWC codes to WasteType enums

    Args:
        ewc_dict: Dictionary mapping EWC codes to their descriptions

    Returns:
        Dictionary mapping EWC codes to WasteType enums
    """
    return {ewc_code: WasteType[ewc_code] for ewc_code in ewc_dict if ewc_code in WasteType.__members__}

def tonnes_to_cubic_meters(tonnes: float, waste_type: WasteType) -> float:
    """
    Convert tonnes to cubic meters for a specific waste type
    
    Args:
        tonnes: Amount in tonnes
        waste_type: Type of waste (determines density)
    
    Returns:
        Volume in cubic meters (m³)
    """
    if waste_type not in WASTE_DENSITIES:
        raise ValueError(f"Unknown waste type {waste_type}, cannot determine density for conversion.")
    else:
        density_kg_m3 = WASTE_DENSITIES[waste_type]
    
    # Convert tonnes to kg, then to m³
    kg = tonnes * 1000.0
    cubic_meters = kg / density_kg_m3
    
    return cubic_meters

def cubic_meters_to_tonnes(cubic_meters: float, waste_type: WasteType) -> float:
    """
    Convert cubic meters to tonnes for a specific waste type
    
    Args:
        cubic_meters: Volume in cubic meters
        waste_type: Type of waste (determines density)
    
    Returns:
        Mass in tonnes
    """
    if waste_type not in WASTE_DENSITIES:
        # Default density for unknown waste types
        density_kg_m3 = 400.0
        print(f"Warning: Unknown waste type {waste_type}, using default density {density_kg_m3} kg/m³")
    else:
        density_kg_m3 = WASTE_DENSITIES[waste_type]
    
    # Convert m³ to kg, then to tonnes
    kg = cubic_meters * density_kg_m3
    tonnes = kg / 1000.0
    
    return tonnes

def get_waste_density(waste_type: WasteType) -> float:
    """
    Get density for a waste type in kg/m³
    
    Args:
        waste_type: Type of waste
    
    Returns:
        Density in kg/m³
    """
    return WASTE_DENSITIES.get(waste_type, 400.0)

def convert_generation_rates_to_volume(
    generation_rates_tonnes: Dict[str, float], 
    waste_type_mapping: Optional[Dict[str, WasteType]] = None
) -> Dict[WasteType, float]:
    """
    Convert waste generation rates from tonnes/day to m³/day
    
    Args:
        generation_rates_tonnes: Dict mapping EWC codes to tonnes/day
        waste_type_mapping: Optional dict mapping EWC codes to WasteType enums.
                          If not provided, will auto-generate from EWC codes.
    
    Returns:
        Dict mapping WasteType to m³/day
    """
    if waste_type_mapping is None:
        waste_type_mapping = {}
        for ewc_code in generation_rates_tonnes.keys():
            try:
                normalized_code = ewc_code.replace(" ", "_").upper()
                for waste_type in WasteType:
                    if waste_type.name.endswith(normalized_code):
                        waste_type_mapping[ewc_code] = waste_type
                        break
            except Exception as e:
                raise ValueError(f"Could not map EWC code {ewc_code}: {e}")
    
    volume_rates = {}
    
    for ewc_code, tonnes_per_day in generation_rates_tonnes.items():
        if ewc_code in waste_type_mapping:
            waste_type = waste_type_mapping[ewc_code]
            volume_per_day = tonnes_to_cubic_meters(tonnes_per_day, waste_type)
            volume_rates[waste_type] = volume_per_day
        else:
            print(f"Warning: EWC code {ewc_code} not found in waste type mapping")
    
    return volume_rates