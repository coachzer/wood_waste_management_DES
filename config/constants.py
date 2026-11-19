from models.enums import OutputType, WasteType

LANDFILL_EMISSIONS_PER_M3_KG = 0.24 * 1_000  # 240 kg CO2e / m³ (0.24 t CO2e per m³)
TRANSPORT_EMISSIONS_PER_TON_KM = 0.087  # kg eCO2 per ton-kilometer or 87 g CO2e/ton km

KILOGRAMS_PER_TONNE = 1000.0  # unit conversion factor, kg per tonne
LANDFILL_COST_PER_TONNE_USD = 46.0  # $/tonne deterrent gate cost, at par with EU-27 landfill range ~EUR 39-46/t (CEWEP 2021 / EEA 2023)
EXPANSION_COST_PER_M3 = 100.0
EXPANSION_COST_ESCALATION_PER_PRIOR = 0.5
LANDFILL_COST_ESCALATION_PER_PRIOR = 0.3

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
# Road km per great-circle km for transport cost and emissions (ADR 0038). Separate from the
# scenario's transportation_time, which scales travel time only (ADR 0015).
ROAD_CIRCUITY_FACTOR = 1.35

COLLECTOR_TRIP_COST_CAP = 100
COLLECTION_CENTER_CAPACITY_MULTIPLE = 2
VEHICLES_PER_COLLECTOR = 3

# Pressed panel density, kg/m3: the midpoint of each product's range in models/products.py
# (particle board 600-800, OSB 600-680, MDF 500-1000). Treatment converts waste mass, not loose
# waste volume, into panel volume with these (ADR 0043). Resin and additive mass is not counted.
PANEL_DENSITIES = {
    OutputType.PARTICLE_BOARD: 700.0,
    OutputType.OSB: 640.0,
    OutputType.MDF: 750.0,
}

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
RECOVERING_BASE_EFFICIENCY = 0.3
# Entity failures are rolled on their own daily clock, independent of each
# entity's main-loop cadence, so FailureConfig.probability is a per-day rate.
FAILURE_CHECK_INTERVAL_DAYS = 1.0
# Treatment processing capacity is sized as this fraction of waste storage capacity.
PROCESSING_CAPACITY_FRACTION = 0.8

# Operating clock (ADR 0020). Treatment and collectors act once per tick. The
# region data keeps each entity's capacity per its native period
# (processing_time / collection_frequency days); the per-tick capacity is that
# capacity * OPERATING_TICK_DAYS / period, so annual capacity is unchanged.
OPERATING_TICK_DAYS = 1.0

# Kanban demand signals older than this many simulation days are pruned, so
# stale demand cannot trigger collection long after it was raised. Sized to the
# slowest signal consumer's tick (ADR 0020): every consumer (treatment,
# collectors, generators) now reads the bus once per OPERATING_TICK_DAYS, and a
# PULL operator absorbs market signals into its backlog even while FAILED, so
# one tick is enough for every signal to be seen once. Level-based signals
# (treatment reorders, generator stock) are re-raised every tick, so keeping
# older copies would only let a collector act on superseded gaps.
KANBAN_SIGNAL_MAX_AGE_DAYS = OPERATING_TICK_DAYS

COLLECTOR_UTILIZATION_CEILING = 0.80
PUSH_COLLECTOR_THRESHOLD_BUFFER = 0.10
PUSH_ON_DEMAND_GENERATOR_SIGNAL_STORAGE_SHARE = 0.1

SAME_REGION_COLLECTION_DISTANCE_KM = 10.0
SAME_REGION_DISTANCE_VARIATION_RANGE = (0.5, 1.5)

# ON_DEMAND collector should-collect threshold: grows with elapsed time, capped
# (core/strategies/stock_strategy.py).
ON_DEMAND_COLLECTOR_BASE_THRESHOLD = 0.10
ON_DEMAND_COLLECTOR_THRESHOLD_GROWTH_PER_DAY = 0.001
ON_DEMAND_COLLECTOR_MAX_THRESHOLD_GROWTH = 0.3

SSD_FLOATING_ACCUMULATION_RELATIVE_TOLERANCE = 1e-9

# Transformation-selection scoring (ADR 0002, Phase F). The ABC priority weight
# enters the score at this multiplier, making it the dominant term (GLOSSARY.md
# "ABC Classification"); the input-availability term saturates at 1.0 once
# on-hand input waste reaches this volume.
ABC_PRIORITY_SCORE_MULTIPLIER = 2.0
INPUT_AVAILABILITY_SATURATION_M3 = 100.0

# Collector base efficiency wears down linearly with elapsed simulation time
# (equipment aging): 1 - t * rate, floored. At this rate a 365-day run ends
# around 0.82, so the floor only binds on longer horizons.
COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY = 0.0005
COLLECTOR_DEGRADATION_FLOOR = 0.5
SEASONAL_PERIODS = 4
SEASONAL_AMPLITUDE = 0.2  # +/- fraction of the seasonal sinusoid about a unit mean
TRAVEL_SPEED_KMH = 50.0

# Market consumption (demand-as-continuous-consumption model, ADR 0002)
WEEKS_PER_YEAR = 52  # annual demand is spread across this many consumption ticks
CONSUMPTION_INTERVAL_DAYS = 7  # the market consumes finished goods weekly

# Treatment order-up-to level S (ADR 0027): S = D*n + z*sigma*sqrt(n), with D the
# waste needed per consumption interval, n the consumption intervals in the
# protection period (lead time + review period, at least one), and sigma the
# seasonal standard deviation of D. Treatment intake is drained from collectors
# within the tick, so the replenishment lead time is zero.
SAFETY_STOCK_Z = 1.645  # 95% cycle service level
TREATMENT_REPLENISHMENT_LEAD_TIME_DAYS = 0.0

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

# Visualization theme. Enum-keyed figure styling lives in visualization/figure_style.py.
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