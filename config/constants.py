from models.enums import WasteType

LANDFILL_EMISSIONS_PER_M3_KG = 0.24 * 1_000  # 240 kg CO2e / m³ (0.24 t CO2e per m³)
TRANSPORT_EMISSIONS_PER_TON_KM = 0.087  # kg eCO2 per ton-kilometer or 87 g CO2e/ton km

KILOGRAMS_PER_TONNE = 1000.0  # unit conversion factor, kg per tonne
LANDFILL_COST_PER_TONNE_USD = 46.0  # $/tonne deterrent gate cost, at par with EU-27 landfill range ~EUR 39-46/t (CEWEP 2021 / EEA 2023)

# Carbon shadow price applied to treatment emissions to derive an environmental
# cost component. Uncalibrated placeholder (the source comment tagged it "example");
# flag for the paper before any cost number leans on it.
CARBON_PRICE_EUR_PER_KG_CO2E = 0.05

# Waste-side inventory holding cost, $/m3 per day, accrued on stored waste at
# every echelon (generator, collector, treatment waste storage) by the daily
# monitor sample (~$1.83/m3-year). Uncalibrated placeholder like CARBON_PRICE
# above; flag for the paper before any cost number leans on it, and restate
# with the currency work (.scratch/currency-consistency/).
WASTE_HOLDING_COST_PER_M3_PER_DAY = 0.005

# Per-km collection transport cost rates. The two are distinct: the realized cost
# scales with both distance and the volume actually collected, while the pre-trip
# estimate uses a flat per-km rate (no volume known yet).
COLLECTION_COST_PER_KM_PER_M3 = 0.1  # realized: distance * this * collected volume
ESTIMATED_COLLECTION_COST_PER_KM = 0.5  # pre-trip estimate: distance * this

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

# Shared base seed: grid mode uses it directly; Monte Carlo replication i uses
# base + i (CRN), so a grid run reproduces MC replication 0 of the same combo.
DEFAULT_BASE_SEED = 123456

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
# Treatment processing capacity is sized as this fraction of waste storage capacity.
PROCESSING_CAPACITY_FRACTION = 0.8
# Collection centers take longer to repair than other entities (days of downtime).
COLLECTION_CENTER_DOWNTIME_DAYS = 2.0

# Kanban demand signals older than this many simulation days are pruned, so
# stale demand cannot trigger collection long after it was raised.
KANBAN_SIGNAL_MAX_AGE_DAYS = 24.0

# Transformation-selection scoring (ADR 0002, Phase F). The ABC priority weight
# enters the score at this multiplier, making it the dominant term (CONTEXT.md
# "ABC Classification"); the input-availability term saturates at 1.0 once
# on-hand input waste reaches this volume.
ABC_PRIORITY_SCORE_MULTIPLIER = 2.0
INPUT_AVAILABILITY_SATURATION_M3 = 100.0

# Collector base efficiency wears down linearly with elapsed simulation time
# (equipment aging): 1 - t * rate, floored. At this rate a 365-day run ends
# around 0.82, so the floor only binds on longer horizons.
COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY = 0.0005
COLLECTOR_DEGRADATION_FLOOR = 0.5
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

# Visualization theme. Encoding convention for the Plotly comparison suite:
# color encodes the inventory policy, marker symbol encodes the stock strategy.
# (The Matplotlib paper figure in policy_comparison_figure.py keeps its own
# documented caption convention: marker per policy, colour per strategy.)
POLICY_COLORS = {"push": "#1f77b4", "pull": "#ff7f0e"}
STRATEGY_SYMBOLS = {"on_demand": "circle", "reorder_50": "square", "reorder_90": "diamond"}
# Positional palette for multi-panel bar charts (Plotly default category colors).
CHART_PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

# Storage-utilization heatmaps: entity timestamps are resampled onto this many
# interpolation points; all utilization heatmaps share one fixed percent scale.
HEATMAP_TIME_GRID_POINTS = 50
HEATMAP_COLORSCALE = "RdYlBu_r"
UTILIZATION_PCT_MIN = 0
UTILIZATION_PCT_MAX = 100
HEATMAP_SUBPLOT_HEIGHT_PX = 300  # per-strategy subplot height in grouped heatmaps
HEATMAP_HEIGHT_PADDING_PX = 100  # title/margin allowance added once per grouped heatmap

# Figure export dimensions.
WIDE_EXPORT_WIDTH_PX = 1600  # PDF export width for grouped heatmaps and the Sankey
PDF_EXPORT_SCALE = 2  # raster scale multiplier for PDF exports
DASHBOARD_HEIGHT_PX = 800
SANKEY_HEIGHT_PX = 600
FRONTIER_FIGURE_WIDTH_PX = 1000
FRONTIER_FIGURE_HEIGHT_PX = 800

# Sankey noise thresholds: nodes/links below these volumes are dropped.
MFA_MIN_NODE_VOLUME_M3 = 1.0
MFA_MIN_FLOW_VOLUME_M3 = 0.1