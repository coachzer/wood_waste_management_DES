# Wood Waste Management DES

SimPy discrete event simulation of wood waste management in Slovenia. Generators in 12 statistical regions produce EWC-coded waste, transport companies collect it, and treatment operators turn it into wood-based panels (MDF, particle board, OSB). Monte Carlo analysis runs across every combination of inventory policy and stock strategy.

## Motivation

Slovenia's wood processing industry produces large volumes of waste wood. This simulation measures how supply chain coordination affects service level, emissions and cost across the national waste-to-product pipeline. It compares push (make-to-stock) and pull (consumption-driven) inventory policies, each combined with three stock strategies that decide when upstream replenishment fires.

## Supply chain structure

The simulation models a three-echelon supply chain:

```
WasteGenerator --> CollectorCompany --> TreatmentOperator --> Market
  (12 regions)     (transport firms)    (panel producers)    (continuous consumption)
```

- **Waste generators** produce EWC-coded waste streams (construction wood, packaging, municipal, etc.) at stochastic rates with seasonal variation.
- **Collector companies** send vehicles to collect waste from generators in their region and deliver it to treatment facilities.
- **Treatment operators** transform collected waste into finished products (MDF, particle board, OSB) through transformation pathways with energy, efficiency and yield parameters.
- **Market consumption** removes finished goods from treatment operators every week, in proportion to each facility's processing capacity.

## Experimental design

The simulation runs a full factorial over two dimensions:

| Dimension | Options |
|---|---|
| Inventory policy | `PUSH` (make-to-stock, threshold-driven) / `PULL` (consumption-event-driven) |
| Stock strategy | `ON_DEMAND` (lot-for-lot) / `REORDER_50` (reorder at 50% capacity) / `REORDER_90` (reorder at 90% capacity) |

That gives 6 policy-strategy combinations per scenario. In baseline mode, each combination runs N replications. Replication `i` uses the same seed in every combination (common random numbers), so combinations can be compared pairwise.

### Inventory policies

**PUSH.** Each entity decides from its own observable state. Treatment operators detect inventory drops through stock strategy thresholds and produce on their own. No events flow from downstream to upstream.

**PULL.** Consumption events from the market trigger production. When the market consumes product, the treatment operator receives a signal and produces to match. The stock strategy then gates upstream waste replenishment. If waste storage drops below the threshold, the operator signals collectors, and collectors signal generators.

### Stock strategies

All three strategies set *when* upstream replenishment signals fire:

- `ON_DEMAND` signals for the replacement volume after every consumption (lot-for-lot).
- `REORDER_50` signals when waste storage drops below 50% of capacity.
- `REORDER_90` signals when waste storage drops below 90% of capacity.

The order-up-to level is always full capacity. Strategy affects waste-side decisions only, not finished goods production.

## Key mechanisms

### ABC classification

Products are ranked by total biogenic carbon stock impact (demand volume times biogenic carbon per unit) and classified with Pareto thresholds. Class A covers cumulative impact up to 70% (priority weight 1.0), class B up to 95% (weight 0.7), and class C the remainder (weight 0.4). The current classification is OSB = A, particle board = B, MDF = C. Priority weights enter transformation scoring with a 2.0x multiplier, so ABC class is the dominant factor when a treatment operator can make more than one product.

### Demand and consumption

`data/demand.json` gives annual demand per product type. The market consumes `(annual_demand / 52) * seasonal_factor` of each product every week, split across operators by processing capacity share. Unfulfilled demand is a lost sale, with no backlog.

### Failure injection

All entities inherit a three-state lifecycle (`OPERATIONAL -> FAILED -> RECOVERING`) from `OperationalEntity`. Scenarios set failure rates and recovery times through `FailureConfig` and `UncertaintySet`.

### Storage and overflow

When waste exceeds storage capacity, the entity compares the cost of expanding storage with the cost of landfilling the overflow and takes the cheaper option. Each repeat expansion costs 50% more than the base price per earlier expansion, and each repeat landfill 30% more per earlier landfill. `WasteMonitor` records overflow events.

### Service level

Two metrics come from the consumption event log:

- `full_service_level` = `consumed / attempted`. This is the headline metric and includes structural capability gaps.
- `operational_service_level` = `consumed / (attempted - no_capability_lost)`. This diagnostic measures policy performance on demand the system can fulfill.

## Running

```bash
# Grid mode: 1 run per policy x strategy combination
python main.py

# Monte Carlo: 100 replications per combination
python main.py --mode baseline --replications 100

# Single scenario with 50 replications, on 4 worker processes
python main.py --mode baseline --scenario Baseline --replications 50 --workers 4
```

`--workers` changes only wall-clock time. Artifacts are byte-identical at any worker count.

### Output

Baseline mode writes to `outputs/baseline/{scenario}/`. Each `{policy}__{strategy}/` subdirectory holds `run_NNN.json` (per-replication KPIs), `raw_NNN.json` (monitor history) and `summary.csv` (per-combination means and confidence intervals). The scenario directory also gets cross-combination results: `paired_comparison.csv`, `stochastic_dominance.csv`, `pareto_frontier.*` and comparison figures as PDF. Grid mode saves MFA visualizations (Plotly HTML) to `plots/`.

## Project structure

```
main.py                     Entry point and CLI
config/
  base_config.py            Scenario definitions, cost params, UncertaintySet
  constants.py              Simulation duration, emission factors, densities, thresholds
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
  data_classes.py           OperationalEntity base, FailureConfig
  enums.py                  WasteType (EWC codes), OutputType, policies, strategies
  transformations.py        Transformation catalogue and waste-to-output pathways
  products.py               Product specifications with biogenic carbon values
  state.py                  SimulationState, one instance per run (entity refs, demand tracking)
  distances.py              Inter-region distance calculations
  facility_data.py          Region JSON loader
data/
  demand.json               National annual demand per product type
  regions/                  One JSON per statistical region (12 files)
  slovenian_cities_distance_matrix_km.csv
instrumentation/
  waste_monitor.py          Per-entity tracking of volumes, costs, emissions, events
  history_store.py          Time-series storage for monitor samples
  mass_balance.py           Mass balance accounting across the pipeline
analysis/
  baseline_aggregate.py     KPI extraction from monitor history
  paired_comparison.py      CRN-paired t-tests and Holm-Bonferroni correction
  bullwhip.py               Throughput bullwhip CV^2 ratios
  stochastic_dominance.py   FSD/SSD distribution comparisons
  flow_times.py             Time-weighted WIP via Little's Law
  pareto.py                 Pareto frontier across combinations
visualization/
  scenario_comparison.py    Cross-scenario KPI charts
  temporal_comparison.py    Time-series inventory and flow plots
  policy_comparison_figure.py  Push vs pull summary figure
  kpi_family_figures.py     Per-KPI family chart sets
utils/
  unit_conversion.py        Tonnes to m3 conversion
  capacity_utils.py         Storage overflow decision logic
  seasonality.py            Quarterly seasonal factor
```

## Dependencies

- Python 3.10+
- SimPy >= 4.1.0
- pandas >= 2.0.0
- NumPy >= 1.24.0
- Plotly >= 5.17.0
- SciPy >= 1.10.0
- Matplotlib >= 3.7.0
- pytest >= 7.0.0 (tests only)

Install with `pip install -r requirements.txt`.

## Units and conventions

- Waste volumes are in m3, converted from tonnes with a per-waste-type density (`WASTE_DENSITIES` in `config/constants.py`).
- Simulation time is in days, 0 to 365.
- Waste types use EWC codes as enum values (e.g., `17 02 01` for construction wood).
- Each simulation run is seeded, and per-entity RNGs derive from `numpy.random.SeedSequence`.
- Numeric constants live in `config/constants.py`.
