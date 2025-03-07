from enum import Enum

class RegionType(Enum):
    POMURSKA = "pomurska"
    PODRAVSKA = "podravska"
    KOROSKA = "koroska"
    SAVINJSKA = "savinjska"
    ZASAVSKA = "zasavska"
    POSAVSKA = "posavska"
    JUGOVZHODNA_SLOVENIJA = "jugovzhodna_slovenija"
    OSREDNJESLOVENSKA = "osrednjeslovenska"
    GORENJSKA = "gorenjska"
    PRIMORSKONOTRANJSKA = "primorskonotranjska"
    GORISKA = "goriska"
    OBALNO_KRASKA = "obalno-kraska"

class WasteType(Enum):
    BARK_WASTE = "bark_waste"           # 03 01 01 & 03 03 01 combined
    SAWDUST = "sawdust"                 # Part of 03 01 05
    WOOD_CUTTINGS = "wood_cuttings"     # Part of 03 01 05
    CONSTRUCTION_WOOD = "construction_wood"  # 17 02 01
    MIXED_WOOD = "mixed_wood"           # 20 01 38
    WOODEN_PACKAGING = "wooden_packaging"    # 15 01 03 (output)
    PAPER_PACKAGING = "paper_packaging"      # 15 01 01 (output)
