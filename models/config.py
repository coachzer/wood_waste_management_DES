from optimization.stochastic import UncertaintySet
from models.enums import WasteType

SIMULATION_DURATION = 200

# Define uncertainty sets for different scenarios
uncertainty_sets = {
    "Baseline": UncertaintySet(
        waste_generation={
            WasteType.SAWDUST: (1.0, 0.2),
            WasteType.WOOD_CUTTINGS: (1.0, 0.2),
            WasteType.BARK: (1.0, 0.2),
            WasteType.CORK: (1.0, 0.2),
            WasteType.SOLID_WOOD: (1.0, 0.2),
            WasteType.PAPER_PACKAGING: (1.0, 0.2),
            WasteType.WOOD_PACKAGING: (1.0, 0.2),
            WasteType.MIXED_WOOD: (1.0, 0.2),
        },
        collection_efficiency=(0.85, 0.1),
        treatment_conversion={waste_type: (0.9, 0.05) for waste_type in WasteType},
        transportation_time=(2.0, 0.5),
        market_demand={waste_type: (1.0, 0.2) for waste_type in WasteType},
        equipment_failure_rate=0.05,
    ),
    "High Uncertainty": UncertaintySet(
        waste_generation={
            WasteType.SAWDUST: (1.0, 0.4),
            WasteType.WOOD_CUTTINGS: (1.0, 0.4),
            WasteType.BARK: (1.0, 0.4),
            WasteType.CORK: (1.0, 0.4),
            WasteType.SOLID_WOOD: (1.0, 0.4),
            WasteType.PAPER_PACKAGING: (1.0, 0.4),
            WasteType.WOOD_PACKAGING: (1.0, 0.4),
            WasteType.MIXED_WOOD: (1.0, 0.4),
        },
        collection_efficiency=(0.85, 0.2),
        treatment_conversion={waste_type: (0.9, 0.1) for waste_type in WasteType},
        transportation_time=(2.0, 1.0),
        market_demand={waste_type: (1.0, 0.4) for waste_type in WasteType},
        equipment_failure_rate=0.1,
    ),
    "High Demand": UncertaintySet(
        waste_generation={
            WasteType.SAWDUST: (1.5, 0.3),
            WasteType.WOOD_CUTTINGS: (1.5, 0.3),
            WasteType.BARK: (1.5, 0.3),
            WasteType.CORK: (1.5, 0.3),
            WasteType.SOLID_WOOD: (1.5, 0.3),
            WasteType.PAPER_PACKAGING: (1.5, 0.3),
            WasteType.WOOD_PACKAGING: (1.5, 0.3),
            WasteType.MIXED_WOOD: (1.5, 0.3),
        },
        collection_efficiency=(0.85, 0.15),
        treatment_conversion={waste_type: (0.9, 0.05) for waste_type in WasteType},
        transportation_time=(2.0, 0.7),
        market_demand={waste_type: (1.5, 0.3) for waste_type in WasteType},
        equipment_failure_rate=0.05,
    ),
    "Optimistic": UncertaintySet(
        waste_generation={
            WasteType.SAWDUST: (1.2, 0.1),
            WasteType.WOOD_CUTTINGS: (1.2, 0.1),
            WasteType.BARK: (1.2, 0.1),
            WasteType.CORK: (1.2, 0.1),
            WasteType.SOLID_WOOD: (1.2, 0.1),
            WasteType.PAPER_PACKAGING: (1.2, 0.1),
            WasteType.WOOD_PACKAGING: (1.2, 0.1),
            WasteType.MIXED_WOOD: (1.2, 0.1),
        },
        collection_efficiency=(0.95, 0.05),
        treatment_conversion={waste_type: (0.95, 0.03) for waste_type in WasteType},
        transportation_time=(1.5, 0.3),
        market_demand={waste_type: (1.2, 0.1) for waste_type in WasteType},
        equipment_failure_rate=0.02,
    ),
}

# Scenario configuration including both uncertainty sets and operational parameters
scenarios = {
    "Baseline": {
        "uncertainty_set": uncertainty_sets["Baseline"],
        "collaboration": False,
    },
    "High Uncertainty": {
        "uncertainty_set": uncertainty_sets["High Uncertainty"],
        "collaboration": True,
    },
    "High Demand": {
        "uncertainty_set": uncertainty_sets["High Demand"],
        "collaboration": True,
    },
    "Optimistic": {
        "uncertainty_set": uncertainty_sets["Optimistic"],
        "collaboration": True,
    },
}
