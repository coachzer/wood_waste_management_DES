from enum import Enum, auto
from typing import Union, Dict

class CollectorParams(Enum):
    """Valid parameters that can be adjusted for collectors"""
    COLLECTION_FREQUENCY = auto()
    EFFICIENCY = auto()

class TreatmentParams(Enum):
    """Valid parameters that can be adjusted for treatment operators"""
    PROCESSING_TIME = auto()
    CONVERSION_RATE = auto()

# Map enum values to actual attribute names
PARAM_MAPPING: Dict[Enum, str] = {
    CollectorParams.COLLECTION_FREQUENCY: "collection_frequency",
    CollectorParams.EFFICIENCY: "efficiency",
    TreatmentParams.PROCESSING_TIME: "processing_time",
    TreatmentParams.CONVERSION_RATE: "conversion_rate"
}

# Valid parameter types
ParamTypes = Union[CollectorParams, TreatmentParams]

def get_param_name(param: ParamTypes) -> str:
    """Get the actual attribute name for a parameter enum value"""
    return PARAM_MAPPING[param]

def validate_adjustment(param: ParamTypes, value: float) -> float:
    """Validate and potentially adjust parameter values to ensure they stay within valid ranges"""
    if param in (CollectorParams.EFFICIENCY, TreatmentParams.CONVERSION_RATE):
        return max(0.1, min(value, 2.0))  # Efficiency/rate between 10% and 200%
    elif param == CollectorParams.COLLECTION_FREQUENCY:
        return max(0.5, min(value, 1.5))  # Frequency between 50% and 150%
    elif param == TreatmentParams.PROCESSING_TIME:
        return max(0.1, min(value, 2.0))  # Processing time between 10% and 200%
    return value
