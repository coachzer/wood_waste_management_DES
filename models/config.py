SIMULATION_DURATION = 200

scenarios = {
    "Baseline": {
        "waste_rate_multiplier": 1.0,
        "collection_efficiency_multiplier": 1.0,
        "collaboration": False,
        "treatment_conversion_rate": 1.0,
    },
    "High Waste Generation": {
        "waste_rate_multiplier": 2.0,
        "collection_efficiency_multiplier": 1.0,
        "collaboration": False,
        "treatment_conversion_rate": 1.0,
    },
    "Improved Collaboration": {
        "waste_rate_multiplier": 1.0,
        "collection_efficiency_multiplier": 1.0,
        "collaboration": True,
        "treatment_conversion_rate": 1.0,
    },
    "High Efficiency": {
        "waste_rate_multiplier": 1.0,
        "collection_efficiency_multiplier": 1.3,
        "collaboration": False,
        "treatment_conversion_rate": 1.2,
    },
}
