# Wood Waste Management DES

SimPy-based discrete event simulation of wood waste management in Slovenia. Models 12 statistical regions generating waste (EWC-coded), collected by transport companies, and treated into wood-based panel products (MDF, particle board, OSB). Supports Monte Carlo analysis across inventory policy and stock strategy combinations.

## Motivation

Slovenia's wood processing industry generates significant volumes of waste wood. This simulation evaluates how different supply chain coordination strategies affect service levels, environmental impact, and operational costs across the national waste-to-product pipeline. The model compares push (make-to-stock) vs. pull (consumption-driven) inventory policies, each combined with three stock strategies that control when upstream replenishment is triggered.

## Supply Chain Structure

The simulation models a three-echelon supply chain:

```
WasteGenerator --> CollectorCompany --> TreatmentOperator --> Market
  (12 regions)     (transport firms)    (panel producers)    (continuous consumption)
```

- **Waste Generators** produce EWC-coded waste streams (construction wood, packaging, municipal, etc.) at stochastic rates with seasonal variation
- **Collector Companies** dispatch vehicles to collect waste from generators within their operating region and deliver it to treatment facilities
- **Treatment Operators** transform collected waste into finished products (MDF, particle board, OSB) using defined transformation pathways with energy, efficiency, and yield parameters
- **Market Consumption** drains finished goods from treatment operators weekly, proportional to each facility's processing capacity

## Experimental Design

The simulation runs a full factorial across two dimensions:

| Dimension | Options |
|---|---|
| **Inventory Policy** | `PUSH` (make-to-stock, threshold-driven) / `PULL` (consumption-event-driven) |
| **Stock Strategy** | `ON_DEMAND` (lot-for-lot) / `REORDER_50` (reorder at 50% capacity) / `REORDER_90` (reorder at 90% capacity) |

This produces 6 policy-strategy combinations per scenario. In baseline mode, each combination runs N replications with different random seeds for Monte Carlo analysis.

### Inventory Policies

**PUSH**: Each entity reasons from its own observable state. Treatment operators detect inventory drops via stock strategy thresholds and produce autonomously. No downstream-to-upstream event flow.

**PULL**: Production is triggered by explicit consumption events from the market. When the market consumes product, the treatment operator receives a signal and produces to match. The stock strategy then gates upstream waste replenishment: if waste storage drops below the threshold, the operator signals collectors, who signal generators.

### Stock Strategies

All three strategies control *when* upstream replenishment signals fire:

- **ON_DEMAND**: Signal for replacement volume after every consumption (lot-for-lot)
- **REORDER_50**: Signal when waste storage drops below 50% of capacity
- **REORDER_90**: Signal when waste storage drops below 90% of capacity

The order-up-to level is always full capacity. Strategy affects waste-side decisions only, not finished goods production.

## Key Mechanisms

### ABC Classification

Products are ranked by total biogenic carbon stock impact (demand volume times biogenic carbon per unit) and classified using Pareto thresholds: Class A (cumulative impact up to 70%, priority weight 1.0), Class B (up to 95%, weight 0.7), Class C (remainder, weight 0.4). Current classification: OSB = A, particle board = B, MDF = C. Priority weights influence transformation selection with a 2.0x scoring multiplier, making ABC the dominant factor when a treatment operator has multiple production options available.

### Demand and Consumption

Demand is specified as annual totals per product type in `data/demand.json`. The market consumes weekly: `(annual_demand / 52) * seasonal_factor` per product type, distributed across operators by processing capacity share. Unfulfilled demand is a lost sale (no backlog).

### Failure Injection

All entities inherit a three-state lifecycle (`OPERATIONAL -> FAILED -> RECOVERING`) via `OperationalEntity`. Failure rates and recovery times are configurable per scenario through `FailureConfig` and `UncertaintySet`.

### Storage and Overflow

When waste exceeds storage capacity, the system decides between landfill disposal and storage expansion based on dynamic cost comparison. Expansion costs increase with each expansion event; landfill costs increase with usage. Overflow events are tracked by `WasteMonitor`.

### Service Level

Two metrics derived from the consumption event log:
- **full_service_level** = `consumed / attempted` (headline metric, includes structural capability gaps)
- **operational_service_level** = `consumed / (attempted - no_capability_lost)` (diagnostic, measures policy effectiveness on fulfillable demand only)

## Running

```bash
# Grid mode: 1 run per policy x strategy combination
python main.py

# Monte Carlo: 100 replications per combination
python main.py --mode baseline --replications 100

# Single scenario with 50 replications
python main.py --mode baseline --scenario Baseline --replications 50
```

### Output

Results are written to `outputs/baseline/{scenario}/{policy}__{strategy}/`. Each run directory contains configuration snapshots, per-replication data, and aggregated KPIs. MFA visualizations (Plotly HTML) are saved to `plots/`.

## Project Structure

```
main.py                     Entry point and CLI
config/
  base_config.py            Scenario definitions, cost params, uncertainty sets
  constants.py              Simulation duration, emission factors, thresholds
core/
  simulation_manager.py     Orchestrates initialization and run lifecycle
  facility_builder.py       Creates SimPy entities from region JSON data
  generator.py              Waste generation process
  collector.py              Collection and transport process
  treatment.py              Transformation and production process
  kanban_manager.py         Pull-mode signal coordination
  abc_analysis.py           Biogenic carbon ABC classification
  transport_manager.py      Point-to-point transport logistics
models/
  entities.py               Data-only entity dataclasses (loaded from JSON)
  data_classes.py           OperationalEntity base, FailureConfig, UncertaintySet
  enums.py                  WasteType (EWC codes), OutputType, policies, strategies
  products.py               Product specifications with biogenic carbon values
  state.py                  SimulationState singleton (entity refs, demand tracking)
  distances.py              Inter-region distance calculations
  facility_data.py          Region JSON loader
data/
  demand.json               National annual demand per product type
  regions/                  One JSON per statistical region (12 files)
  slovenian_cities_distance_matrix_km.csv
monitoring/
  waste_monitor.py          Per-entity tracking of volumes, costs, emissions, events
  baseline_aggregate.py     KPI extraction from monitor history
  scenario_comparison.py    Cross-scenario analysis
  visualization/            Plotly-based charts and temporal comparisons
utils/
  unit_conversion.py        Tonnes to m3 conversion
  capacity_utils.py         Storage overflow decision logic
  helpers.py                Shared utilities
```

## Dependencies

- Python 3.10+
- SimPy >= 4.1.0
- pandas >= 2.0.0
- NumPy >= 1.24.0
- Plotly >= 5.17.0

Install: `pip install -r requirements.txt`

## Units and Conventions

- Waste volumes in **m3** (converted from tonnes via density factor 0.6 t/m3)
- Simulation time in **days** (0-365)
- Waste types use **EWC codes** as enum values (e.g., `17 02 01` for construction wood)
- Each simulation run is deterministically seeded; per-entity RNGs propagate via `numpy.random.SeedSequence`
- All magic numbers live in `config/constants.py`
