from enum import Enum, auto

class EntityStatus(Enum):
    """Status of operational entities in the system."""
    OPERATIONAL = auto()   # Entity is functioning normally
    FAILED = auto()        # Entity has experienced a failure
    RECOVERING = auto()    # Entity is in recovery phase after failure

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
    OBALNO_KRASKA = "obalno_kraska"

class WasteType(Enum):
    # 02 - Agricultural, horticultural, aqua cultural, forestry, hunting, and fishing waste
    FORESTRY_WASTE_02_01_07 = "02 01 07"
    # 03 - Wood processing, panel & furniture production, paper & cardboard waste
    BARK_CORK_WASTE_03_01_01 = "03 01 01"
    SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05 = "03 01 05"
    OTHER_WOOD_WASTE_03_01_99 = "03 01 99"
    BARK_WOOD_WASTE_03_03_01 = "03 03 01"
    PAPER_CARDBOARD_SORTING_WASTE_03_03_08 = "03 03 08"
    # 15 - Waste packaging
    PAPER_PACKAGING_15_01_01 = "15 01 01"
    WOODEN_PACKAGING_15_01_03 = "15 01 03"
    # 17 - Construction & demolition waste 
    CONSTRUCTION_WOOD_17_02_01 = "17 02 01"
    # 19 - Waste from waste treatment, water treatment, and water preparation
    PAPER_CARDBOARD_19_12_01 = "19 12 01"
    WOOD_19_12_07 = "19 12 07"
    # 20 - Municipal waste 
    PAPER_CARDBOARD_20_01_01 = "20 01 01"
    NON_HAZARDOUS_WOOD_20_01_38 = "20 01 38"
    BULKY_WASTE_20_03_07 = "20 03 07"

class OutputType(Enum):
    """Types of output products produced by the system."""
    MDF = "mdf"     
    PARTICLE_BOARD = "particle_board"
    OSB = "osb"

class InventoryPolicy(Enum):
    PUSH = "push"
    PULL = "pull"

    def is_pull(self) -> bool:
        return self is InventoryPolicy.PULL

class StockStrategy(Enum):
    ON_DEMAND = "on_demand"
    REORDER_90 = "reorder_90"
    REORDER_50 = "reorder_50"
