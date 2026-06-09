from models.enums import WasteType

LANDFILL_EMISSIONS_PER_M3 = 0.24  # t CO2e per m³
LANDFILL_EMISSIONS_PER_M3_KG = 0.24 * 1_000  # 240 kg CO2e / m³
TRANSPORT_EMISSIONS_PER_TON_KM = 0.087  # kg eCO2 per ton-kilometer or 87 g CO2e/ton km

KILOGRAMS_PER_TONNE = 1000.0  # unit conversion factor, kg per tonne
LANDFILL_COST_PER_TONNE_USD = 46.0  # $/tonne deterrent gate cost, at par with EU-27 landfill range ~EUR 39-46/t (CEWEP 2021 / EEA 2023)

# Standard waste densities in kg/m³ based on EWC codes and industry data
WASTE_DENSITIES = {
    WasteType.FORESTRY_WASTE_02_01_07: 350.0,
    WasteType.BARK_CORK_WASTE_03_01_01: 400.0,
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 200.0,
    WasteType.OTHER_WOOD_WASTE_03_01_99: 450.0,
    WasteType.BARK_WOOD_WASTE_03_03_01: 450.0,
    WasteType.PAPER_CARDBOARD_SORTING_WASTE_03_03_08: 600.0,
    WasteType.PAPER_PACKAGING_15_01_01: 600.0,
    WasteType.WOODEN_PACKAGING_15_01_03: 400.0,
    WasteType.CONSTRUCTION_WOOD_17_02_01: 500.0,
    WasteType.PAPER_CARDBOARD_19_12_01: 600.0,
    WasteType.WOOD_19_12_07: 400.0,
    WasteType.PAPER_CARDBOARD_20_01_01: 600.0,
    WasteType.NON_HAZARDOUS_WOOD_20_01_38: 450.0,
    WasteType.BULKY_WASTE_20_03_07: 300.0
}

# Avoided emissions (C11, ADR 0011): recycling avoided-burden, kg CO2eq / m3.
# Per-product factors from Lao & Chang (2023), biogenic carbon EXCLUDED so the
# C10 biogenic-stored credit is not double-counted.
AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT = {
    "mdf": 406.0,  # Lao 2023 FB (fibreboard class; MDF is the dominant member)
    "particle_board": 348.0,  # Lao 2023 PB
    "osb": 552.0,  # Lao 2023 OSB
}

SIMULATION_DURATION = 365  # days in simulation (one full year)
EXPANSION_SIZE_M3 = 500  # 500m³ expansion size
OVERFLOW_VOLUME_TOLERANCE_M3 = 1e-10  # overflow volumes below this are treated as zero (no_action)

LOCAL_COLLECTION_RATIO = 0.8

# PUSH (s, S) waste-storage reorder thresholds (ADR 0002, signal-volume rule).
# When total waste_storage drops below this fraction of waste_storage_capacity,
# the PUSH trigger fires and orders up to full capacity (S = waste_storage_capacity).
PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_50 = 0.5
PUSH_WASTE_STORAGE_REORDER_THRESHOLD_REORDER_90 = 0.9
FAILED_ENTITY_EFFICIENCY = 0.1
RECOVERING_BASE_EFFICIENCY = 0.3
HISTORY_BUFFER_SIZE = 1000
SEASONAL_PERIODS = 4
SEASONAL_AMPLITUDE = 0.2  # +/- fraction of the seasonal sinusoid about a unit mean
TRAVEL_SPEED_KMH = 50.0

# Market consumption (demand-as-continuous-consumption model, ADR 0002)
WEEKS_PER_YEAR = 52  # annual demand is spread across this many consumption ticks
CONSUMPTION_INTERVAL_DAYS = 7  # the market consumes finished goods weekly

# Inventory priming (ADR 0002, Phase C). Finished-goods capacity per product is
# sized to FINISHED_GOODS_BUFFER_WEEKS of that product's expected consumption;
# initial inventory starts at INITIAL_INVENTORY_FRACTION of capacity, and
# waste storage is primed to WASTE_STORAGE_PRIMING_WEEKS of producible throughput.
FINISHED_GOODS_BUFFER_WEEKS = 4  # weeks of expected demand held as finished-goods capacity
INITIAL_INVENTORY_FRACTION = 0.5  # finished goods start half-full (2 weeks of the 4-week buffer)
WASTE_STORAGE_PRIMING_WEEKS = 2  # weeks of producible throughput primed into waste storage

# Throughput bullwhip metric (ADR 0004). Purely post-hoc: computed from already
# persisted logs and never affects simulation behaviour. Flows and consumption
# are bucketed into BULLWHIP_BIN_WIDTH_DAYS bins; the first BULLWHIP_WARMUP_WEEKS
# weeks (the cold-start ramp) are dropped, so the metric spans weeks 5-52.
BULLWHIP_BIN_WIDTH_DAYS = 7  # weekly bins, aligned with the consumption tick
BULLWHIP_WARMUP_WEEKS = 4  # drop the cold-start ramp before computing CV^2

# Output artifact roots (clean-monitoring issue 12). Single source of truth for
# where the simulation writes run data and plots, so relocating an artifact tree
# touches one place instead of ~5 scattered string literals. Forward slashes are
# portable across platforms for the append-only paths the writers build from these.
OUTPUT_ROOT = "outputs"
PLOTS_ROOT = "plots"
BASELINE_OUTPUT_ROOT = f"{OUTPUT_ROOT}/baseline"
BASELINE_SCENARIO_DEFAULT = f"{BASELINE_OUTPUT_ROOT}/Baseline"
SCENARIO_COMPARISON_PLOTS_DIR = f"{PLOTS_ROOT}/scenario_comparison"