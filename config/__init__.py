"""
Unified configuration package for waste management system.
Single source of truth following KISS principle.
"""

from .base_config import (
    # Core data structures
    UncertaintySet,
    ScenarioConfig,
    
    # Scenario access functions
    get_uncertainty_set,
    get_scenario_config,
    list_available_scenarios,
    
    # Parameter access functions
    get_cost_params,
    
    # Constants
    SIMULATION_DURATION,
    DEFAULT_COSTS
)

__all__ = [
    # Core data structures
    'UncertaintySet',
    'ScenarioConfig', 
    
    # Access functions
    'get_uncertainty_set',
    'get_scenario_config',
    'list_available_scenarios',
    'get_cost_params',
    
    # Constants
    'SIMULATION_DURATION',
    'DEFAULT_COSTS'
]
