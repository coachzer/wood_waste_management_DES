"""
Central configuration management for the wood waste management DES system.
Provides a single entry point for accessing all configuration settings.
"""
from typing import Dict, Any

from .base_config import (
    SIMULATION_DURATION,
    TIME_PERIOD,
    TOTAL_YEARS,
    TIME_PERIODS,
    MONTHLY_DEMAND,
    SCENARIO_CONFIGS,
    ScenarioConfig,
    validate_scenario_config,
    validate_time_periods
)


from .cost_config import (
    CostType,
    CostConfig,
    DEFAULT_COST_CONFIG,
    validate_cost_config
)

from .facility_config import (
    StorageConfig,
    ProcessingConfig,
    TreatmentFacilityConfig,
    DEFAULT_STORAGE_CONFIG,
    DEFAULT_PROCESSING_CONFIG,
    BASE_TRANSFORMATION_EFFICIENCIES,
    create_default_facility_config
)

# Version of the configuration system
CONFIG_VERSION = "1.0.0"

def get_all_configs() -> Dict[str, Any]:
    """Get all configuration settings as a dictionary"""
    return {
        "version": CONFIG_VERSION,
        "simulation": {
            "duration": SIMULATION_DURATION,
            "time_period": TIME_PERIOD,
            "total_years": TOTAL_YEARS,
            "time_periods": TIME_PERIODS
        },
        "scenarios": SCENARIO_CONFIGS,
        "demand": MONTHLY_DEMAND,
        "costs": DEFAULT_COST_CONFIG.to_dict(),
        "facilities": {
            "default_storage": DEFAULT_STORAGE_CONFIG,
            "default_processing": DEFAULT_PROCESSING_CONFIG,
            "base_transformations": BASE_TRANSFORMATION_EFFICIENCIES
        }
    }

def validate_all_configs() -> None:
    """Validate all configuration settings"""
    # Validate time configurations
    validate_time_periods()
    
    # Validate scenario configurations
    for scenario_name, config in SCENARIO_CONFIGS.items():
        validate_scenario_config(config)
    
    # Validate cost configuration
    validate_cost_config(DEFAULT_COST_CONFIG)
    
    # Create and validate a test facility configuration
    test_facility = create_default_facility_config(
        name="Test Facility",
        location=(46.0569, 14.5058)  # Ljubljana coordinates
    )
    test_facility.validate()

# Validate all configurations on import
validate_all_configs()

__all__ = [
    # Version
    'CONFIG_VERSION',
    # Base config
    'SIMULATION_DURATION', 'TIME_PERIOD', 'TOTAL_YEARS', 'TIME_PERIODS',
    'MONTHLY_DEMAND', 'SCENARIO_CONFIGS', 'ScenarioConfig', 'validate_scenario_config',
    # Cost config
    'CostType', 'CostConfig', 'DEFAULT_COST_CONFIG', 'validate_cost_config',
    # Facility config
    'StorageConfig', 'ProcessingConfig', 'TreatmentFacilityConfig',
    'DEFAULT_STORAGE_CONFIG', 'DEFAULT_PROCESSING_CONFIG',
    'BASE_TRANSFORMATION_EFFICIENCIES', 'create_default_facility_config',
    # Utility functions
    'get_all_configs', 'validate_all_configs'
]
