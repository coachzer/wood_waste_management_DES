from models.enums import WasteType
from optimization.stochastic import UncertaintySet

# Import scenario configurations
from config.base_config import SCENARIO_CONFIGS

# Create uncertainty sets from scenario configs
uncertainty_sets = {}
for name, config in SCENARIO_CONFIGS.items():
    # Create waste generation with values appropriate for input types
    waste_generation = {
        # Primary materials
        WasteType.SAWDUST: (4320 * config.waste_gen[0], 864 * config.waste_gen[1]),
        WasteType.WOOD_CUTTINGS: (3780 * config.waste_gen[0], 756 * config.waste_gen[1]),
        WasteType.BARK_WASTE: (2850 * config.waste_gen[0], 570 * config.waste_gen[1]),
        WasteType.CONSTRUCTION_WOOD: (2130 * config.waste_gen[0], 426 * config.waste_gen[1]),
        WasteType.MIXED_WOOD: (2430 * config.waste_gen[0], 486 * config.waste_gen[1]),
        # Recyclable materials
        WasteType.WASTE_WOODEN_PACKAGING: (1800 * config.waste_gen[0], 360 * config.waste_gen[1]),  # Add recyclable packaging
        WasteType.WASTE_PAPER_PACKAGING: (1200 * config.waste_gen[0], 240 * config.waste_gen[1]),
        # Final products (generate no waste)
        WasteType.WOODEN_PACKAGING: (0, 0),
        WasteType.PAPER_PACKAGING: (0, 0),
        WasteType.WOODEN_FURNITURE: (0, 0)
    }

    # Create treatment conversion rates
    treatment_conversion = {waste_type: config.treat_conv for waste_type in WasteType}

    # Create market demand
    market_demand = {
        WasteType.WOODEN_PACKAGING: (600 * config.market_dem[0], 600 * config.market_dem[1]),
        WasteType.PAPER_PACKAGING: (500 * config.market_dem[0], 500 * config.market_dem[1]),
        WasteType.WOODEN_FURNITURE: (200 * config.market_dem[0], 200 * config.market_dem[1]),
    }
    # Add input waste types with lower demand
    for waste_type in WasteType:
        if waste_type not in market_demand:
            market_demand[waste_type] = (600 * config.market_dem[0], 240 * config.market_dem[1])

    # Create uncertainty set
    uncertainty_set = UncertaintySet(
        waste_generation=waste_generation,
        collection_efficiency=config.coll_eff,
        treatment_conversion=treatment_conversion,
        transportation_time=config.trans_time,
        market_demand=market_demand,
        generator_failure=config.generator_failure,
        collector_failure=config.collector_failure,
        treatment_failure=config.treatment_failure
    )
    
    uncertainty_sets[name] = uncertainty_set

# Default uncertainty set (Baseline)
default_uncertainty_set = uncertainty_sets["Baseline"]

# Function to get uncertainty set by scenario name
def get_uncertainty_set(scenario_name: str = "Baseline") -> UncertaintySet:
    """Get uncertainty set for a specific scenario"""
    return uncertainty_sets.get(scenario_name, default_uncertainty_set)
