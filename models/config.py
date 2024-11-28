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

# generator1 = WasteGenerator(
#         env,
#         "Generator A",
#         {WasteType.SAWDUST: 5.0, WasteType.WOOD_CUTTINGS: 5.0},
#         5,
#         50,
#         1,
#         1,
#         0.5,
#         "Moderate",
#         "North",
#     )
# generator2 = WasteGenerator(
#     env,
#     "Generator B",
#     {WasteType.BARK: 8.0, WasteType.CORK: 7.0},
#     8,
#     50,
#     2,
#     0.05,
#     0.1,
#     "Low",
#     "North",
# )
# generator3 = WasteGenerator(
#     env,
#     "Generator C",
#     {WasteType.SOLID_WOOD: 2.0},
#     6,
#     40,
#     3,
#     0.2,
#     0.15,
#     "Low",
#     "East",
# )
# generator4 = WasteGenerator(
#     env,
#     "Generator D",
#     {WasteType.PAPER_PACKAGING: 8.0},
#     4,
#     30,
#     2,
#     0.15,
#     0.05,
#     "Low",
#     "South",
# )
# generator5 = WasteGenerator(
#     env,
#     "Generator E",
#     {WasteType.MIXED_WOOD: 20.0},
#     10,
#     60,
#     1,
#     0.1,
#     0.1,
#     "Low",
#     "South",
# )
# generator6 = WasteGenerator(
#     env,
#     "Generator F",
#     {WasteType.MIXED_WOOD: 18.0},
#     9,
#     55,
#     2,
#     0.05,
#     0.1,
#     "Low",
#     "East",
# )
# generator7 = WasteGenerator(
#     env,
#     "Generator G",
#     {WasteType.WOOD_PACKAGING: 14.0},
#     7,
#     45,
#     1,
#     0.2,
#     0.1,
#     "Low",
#     "North",
# )

# collector1 = CollectorCompany(
#     env, "Collector X", 20, 10, 50, "Low", 0.9, True, "competitive", "North"
# )
# collector2 = CollectorCompany(
#     env, "Collector Y", 30, 15, 70, "Moderate", 0.8, True, "collaborative", "East"
# )
# collector3 = CollectorCompany(
#     env, "Collector Z", 25, 12, 60, "High", 0.85, True, "competitive", "South"
# )
# collector4 = CollectorCompany(
#     env, "Collector W", 22, 11, 55, "Low", 0.75, True, "collaborative", "North"
# )
# collector5 = CollectorCompany(
#     env, "Collector V", 28, 14, 65, "Moderate", 0.95, True, "competitive", "East"
# )

# # Treatment operators initiating demand
# treatment1 = TreatmentOperator(
#     env, "Treatment Plant A", 50, 12, 100, 1.5, "Moderate", 0.8, 10, "North"
# )
# treatment2 = TreatmentOperator(
#     env, "Treatment Plant B", 60, 10, 120, 1.2, "Low", 1, 12, "South"
# )
# treatment3 = TreatmentOperator(
#     env, "Treatment Plant C", 55, 11, 110, 1.3, "High", 0.85, 11, "East"
# )
