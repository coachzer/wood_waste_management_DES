"""
Facility-related configuration settings.
Contains parameters for treatment facilities, storage, and operational characteristics.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from models.enums import WasteType, OutputType
from utils.helpers import validate_all_numeric_positive
from .base_config import MONTHLY_DEMAND

@dataclass
class StorageConfig:
    """Storage facility configuration"""
    initial_capacity: float
    max_capacity: float
    min_capacity: float = 0.0
    overflow_threshold: float = 0.9  # Trigger overflow handling at 90% capacity

    def validate(self) -> None:
        """Validate storage configuration"""
        config_dict = {
            'initial_capacity': self.initial_capacity,
            'max_capacity': self.max_capacity,
            'min_capacity': self.min_capacity
        }
        validate_all_numeric_positive(config_dict, allow_zero=True)
        
        if self.max_capacity < self.initial_capacity:
            raise ValueError("Max capacity must be greater than or equal to initial capacity")
        if not 0 <= self.min_capacity <= self.initial_capacity:
            raise ValueError("Min capacity must be between 0 and initial capacity")
        if not 0 < self.overflow_threshold <= 1:
            raise ValueError("Overflow threshold must be between 0 and 1")

@dataclass
class ProcessingConfig:
    """Processing facility configuration"""
    input_types: List[WasteType]
    output_types: List[WasteType]
    base_efficiency: float = 0.9
    energy_consumption: float = 1.0  # Base energy consumption per unit
    processing_time: float = 1.0     # Base processing time per unit

    def validate(self) -> None:
        """Validate processing configuration"""
        if not self.input_types:
            raise ValueError("At least one input type must be specified")
        if not self.output_types:
            raise ValueError("At least one output type must be specified")
        
        config_dict = {
            'base_efficiency': self.base_efficiency,
            'energy_consumption': self.energy_consumption,
            'processing_time': self.processing_time
        }
        validate_all_numeric_positive(config_dict, allow_zero=False)
        
        # Additional validation for efficiency
        if self.base_efficiency > 1:
            raise ValueError("Base efficiency must be between 0 and 1")

@dataclass
class TreatmentFacilityConfig:
    """Complete treatment facility configuration"""
    name: str
    location: Tuple[float, float]  # lat, long
    storage: StorageConfig
    processing: ProcessingConfig
    maintenance_interval: Optional[int] = None  # Time units between maintenance

    def validate(self) -> None:
        """Validate complete facility configuration"""
        if not self.name:
            raise ValueError("Facility name must not be empty")
        
        lat, long = self.location
        if not (-90 <= lat <= 90 and -180 <= long <= 180):
            raise ValueError("Invalid location coordinates")
            
        self.storage.validate()
        self.processing.validate()
        
        if self.maintenance_interval is not None and self.maintenance_interval <= 0:
            raise ValueError("Maintenance interval must be positive")

# Calculate storage capacity needs based on monthly demand
TOTAL_MONTHLY_DEMAND = sum(MONTHLY_DEMAND.values())  # Total monthly demand for all products
STORAGE_BUFFER_FACTOR = 1.5  # Keep 50% extra capacity for buffers

# Default configurations
DEFAULT_STORAGE_CONFIG = StorageConfig(
    initial_capacity=TOTAL_MONTHLY_DEMAND * STORAGE_BUFFER_FACTOR,  # Enough for one month's total demand plus buffer
    max_capacity=TOTAL_MONTHLY_DEMAND * STORAGE_BUFFER_FACTOR * 1.5,  # 50% more than initial
    min_capacity=TOTAL_MONTHLY_DEMAND * 0.1,  # 10% of monthly demand as minimum
    overflow_threshold=0.9
)

# Input types (raw materials)
DEFAULT_INPUT_TYPES = [
    WasteType.SAWDUST,         # Fine particles for compression
    WasteType.WOOD_CUTTINGS,   # Structural elements
    WasteType.CONSTRUCTION_WOOD,# High-quality material
    WasteType.BARK_WASTE,      # For paper products
    WasteType.MIXED_WOOD,      # For paper products
    WasteType.WASTE_WOODEN_PACKAGING, # Recyclable wood packaging
    WasteType.WASTE_PAPER_PACKAGING  # Recyclable paper packaging
]

# Output types (final products from demand.json)
DEFAULT_OUTPUT_TYPES = [
    OutputType.WOODEN_FURNITURE,   # High-quality furniture products
    OutputType.WOODEN_PACKAGING,   # Industrial packaging products
    OutputType.PAPER_PACKAGING     # Paper-based packaging products
]

DEFAULT_PROCESSING_CONFIG = ProcessingConfig(
    input_types=DEFAULT_INPUT_TYPES,
    output_types=DEFAULT_OUTPUT_TYPES,
    base_efficiency=0.85,  # Slightly reduced for more conservative processing
    energy_consumption=1.0,
    processing_time=1.2    # Slightly longer processing time to avoid overflows
)

# Base transformation efficiencies for different waste types
# Each waste type has a (efficiency, energy_required) tuple that represents how well it can be transformed
# and how much energy is needed for the transformation
BASE_TRANSFORMATION_EFFICIENCIES: Dict[WasteType, Tuple[float, float]] = {
    # Primary materials (best for furniture)
    WasteType.CONSTRUCTION_WOOD: (0.98, 0.90),   # High quality, high energy
    WasteType.WOOD_CUTTINGS: (0.92, 0.85),       # Good quality, high energy
    WasteType.WASTE_WOODEN_PACKAGING: (0.88, 0.95), # Good for furniture after processing
    
    # Secondary materials (good for packaging)
    WasteType.SAWDUST: (0.95, 0.50),             # Great for compression molding
    
    # Paper materials
    WasteType.BARK_WASTE: (0.85, 0.70),          # Good for pulping
    WasteType.MIXED_WOOD: (0.88, 0.60),          # Decent for pulping
    WasteType.WASTE_PAPER_PACKAGING: (0.82, 0.65), # Good for recycling into new paper products
}

def create_default_facility_config(
    name: str,
    location: Tuple[float, float],
    storage_capacity: Optional[float] = None,
    input_types: Optional[List[WasteType]] = None,
    output_types: Optional[List[WasteType]] = None
) -> TreatmentFacilityConfig:
    """Create a facility configuration with optional customization"""
    storage = StorageConfig(
        initial_capacity=storage_capacity or DEFAULT_STORAGE_CONFIG.initial_capacity,
        max_capacity=storage_capacity * 1.5 if storage_capacity else DEFAULT_STORAGE_CONFIG.max_capacity,
        min_capacity=DEFAULT_STORAGE_CONFIG.min_capacity,
        overflow_threshold=DEFAULT_STORAGE_CONFIG.overflow_threshold
    )
    
    processing = ProcessingConfig(
        input_types=input_types or DEFAULT_INPUT_TYPES.copy(),
        output_types=output_types or DEFAULT_OUTPUT_TYPES.copy(),
        base_efficiency=DEFAULT_PROCESSING_CONFIG.base_efficiency,
        energy_consumption=DEFAULT_PROCESSING_CONFIG.energy_consumption,
        processing_time=DEFAULT_PROCESSING_CONFIG.processing_time
    )
    
    facility = TreatmentFacilityConfig(
        name=name,
        location=location,
        storage=storage,
        processing=processing
    )
    
    facility.validate()
    return facility
