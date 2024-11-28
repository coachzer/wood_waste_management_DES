from enum import Enum


class WasteType(Enum):
    SAWDUST = "sawdust"  # Fine particles from cutting/processing
    WOOD_CUTTINGS = "wood_cuttings"  # Larger wood pieces from cutting
    BARK = "bark"  # Tree bark
    CORK = "cork"  # Cork material
    SOLID_WOOD = "solid_wood"  # Untreated solid wood
    PAPER_PACKAGING = "paper_packaging"  # Paper-based packaging
    WOOD_PACKAGING = "wood_packaging"  # Wooden pallets, crates
    MIXED_WOOD = "mixed_wood"  # Mixed wood waste
