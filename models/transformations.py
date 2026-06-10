"""Single source of truth for the waste-to-product transformation catalogue.

Both FacilityBuilder (the live build path) and TreatmentOperator's
no-transformations fallback read these tables; they previously each carried
their own copy and the output mappings had drifted apart.
"""
from models.enums import OutputType, WasteType

# (conversion_efficiency, energy_required) per input waste type.
TRANSFORMATION_CATALOGUE = {
    WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),
    WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95),
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),
    WasteType.BARK_CORK_WASTE_03_01_01: (0.85, 0.70),
    WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),
    WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),
    WasteType.FORESTRY_WASTE_02_01_07: (0.82, 0.75),
    WasteType.OTHER_WOOD_WASTE_03_01_99: (0.85, 0.65),
}

# Output products each input waste type may become.
WASTE_TO_OUTPUT_TYPES = {
    WasteType.CONSTRUCTION_WOOD_17_02_01: [
        OutputType.PARTICLE_BOARD,
        OutputType.OSB,
    ],
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: [
        OutputType.PARTICLE_BOARD,
        OutputType.MDF,
    ],
    WasteType.WOODEN_PACKAGING_15_01_03: [
        OutputType.PARTICLE_BOARD,
        OutputType.OSB,
    ],
    WasteType.BARK_CORK_WASTE_03_01_01: [
        OutputType.MDF,
        OutputType.PARTICLE_BOARD,
    ],
    WasteType.NON_HAZARDOUS_WOOD_20_01_38: [
        OutputType.PARTICLE_BOARD,
        OutputType.MDF,
        OutputType.OSB,
    ],
    WasteType.PAPER_PACKAGING_15_01_01: [
        OutputType.MDF,
    ],
    WasteType.FORESTRY_WASTE_02_01_07: [
        OutputType.PARTICLE_BOARD,
        OutputType.MDF,
    ],
    WasteType.OTHER_WOOD_WASTE_03_01_99: [
        OutputType.PARTICLE_BOARD,
        OutputType.MDF,
        OutputType.OSB,
    ],
}
