# CLAUDE.md

Guidance for Claude Code working in this repository. The domain glossary is @CONTEXT.md. Use its terms exactly.

## Project overview

SimPy discrete event simulation of wood waste management in Slovenia. Generators in 12 statistical regions produce EWC-coded waste, transport companies collect it, and treatment operators turn it into MDF, particle board and OSB. Monte Carlo analysis runs across `InventoryPolicy` (push/pull) × `StockStrategy` (on_demand/reorder_50/reorder_90).

## Running simulations

```bash
python main.py                                        # Grid mode: 1 run per policy×strategy combo
python main.py --mode baseline --replications 100     # Monte Carlo: 100 seeds per combo
python main.py --mode baseline --scenario Baseline --replications 50  # Single scenario
python -m analysis.paired_comparison outputs/baseline/Baseline        # Post-hoc paired (CRN) stats
```

Baseline outputs go to `outputs/baseline/{scenario}/{policy}__{strategy}/`. MFA visualizations (Plotly HTML) go to `plots/`.

**Seeding is Common Random Numbers (CRN).** Baseline replication `i` uses `seed = base_seed + i` for every policy×strategy combo, so all combos see the same waste and failure draws. `summary.csv` reports marginal per-combo CIs. `analysis/paired_comparison.py` uses the pairing (per-replication KPI differences, paired-t CIs, per-metric Holm-Bonferroni) and writes `{scenario}/paired_comparison.csv` after each baseline run.

## Architecture

**Three-layer pipeline.** `WasteGenerator` → `CollectorCompany` → `TreatmentOperator`, all in `core/`. Each inherits `OperationalEntity` (`models/data_classes.py`), which provides failure injection via `FailureConfig` and a three-state lifecycle: `OPERATIONAL → FAILED → RECOVERING`.

**Two entity layers.** `models/entities.py` holds data-only dataclasses loaded from JSON. `core/*.py` holds the SimPy process classes that run in the simulation. Construction order: `SimulationManager.initialize_entities()` → `FacilityDataManager.load_data()` → `FacilityBuilder` (config injected as `ScenarioConfig` → `to_uncertainty_set()`) → `SimulationState.initialize()`. Scenarios live in `SCENARIO_CONFIGS` (`config/base_config.py`).

**Kanban/pull coordination.** `KanbanManager` is active in PULL mode. Treatment signals collectors and collectors signal generators. Signals are consumed in insertion order, with no priority weighting. In PUSH mode, generators emit signals but collectors ignore them and collect by volume.

**ABC prioritization.** `BiogenicCarbonABCAnalyzer` (`core/abc_analysis.py`) ranks products into A/B/C classes (priority weights 1.0/0.7/0.4), which `TreatmentOperator._get_prioritized_transformations()` uses. It is always on, with no enable flag and no per-scenario setting. Inputs are `data/demand.json` and `models/products.py`.

## Known failure modes

- **Reproducibility: sort enum sets.** A given seed must yield byte-identical run JSONs across separate process invocations. Before iterating a set of `WasteType`/`OutputType` on a path that drives ordered work (collection allocation, signal creation, storage priming), `sorted(..., key=lambda e: e.value)` it and pass an ordered `List`. Keep it a `List` downstream. Enum members hash by `id()`, which `PYTHONHASHSEED` does not control, so an unsorted set of enums iterates in per-process memory order and breaks reproducibility without any error. Backstops are `tests/test_enum_set_ordering.py` and `tests/test_determinism.py`.
- **Pull policy deadlock.** Under pull, treatment must trigger collection. If treatment never requests waste, collectors stall. Check that `TreatmentOperator._should_trigger_collection_based_on_strategy()` fires (threshold logic is in `core/strategies/stock_strategy.py`).
- **KPIs.** `analysis/baseline_aggregate.py::extract_kpis()` extracts them from monitor history dicts.

## Key conventions

- **Units.** Waste volumes are in m³, converted from tonnes via `utils/unit_conversion.py`. Simulation time is in days, 0 to 365.
- **Seeding.** `run_single_simulation()` calls `random.seed(s)` and `np.random.seed(s)`. Per-entity RNGs come from `np.random.SeedSequence`, passed from `SimulationManager` to `FacilityBuilder` to each entity.
- **Waste types.** EWC codes are the enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations are keyed by `(WasteType, OutputType)`.
- **Storage overflow.** Waste above `waste_storage_capacity` goes to landfill, tracked in `WasteMonitor`. Treatment can expand storage (`EXPANSION_SIZE_M3 = 500`).
- **Region data.** One JSON per region in `data/regions/`. Distances come from `models/distances.py::get_distance()`.
- **Constants.** All live in `config/constants.py`. Other modules name a constant from there instead of a literal number.
- **Variable naming.** Verbose and descriptive, never abbreviated (`waste_storage_capacity`, not `wsc`).
- **No emojis** in code or comments.
- **Surgical changes.** Touch only what the task needs. For adjacent working code that could be refactored, open a ticket. If a review check fails, stop and open an issue instead of expanding scope.
- **Commits.** Imperative mood, under 72 chars, no colon after the verb (`Add`, `Fix`, `Refactor`, `Update`, `Remove`, `Improve`). The body, after a blank line, explains *why*, not *what*. A commit that needs a semicolon is probably two commits.

## Adding new waste types or products

1. Add the enum to `models/enums.py::WasteType` (EWC format) or `OutputType`.
2. Add the efficiency/energy row to `TRANSFORMATION_CATALOGUE` and the output pathways to `WASTE_TO_OUTPUT_TYPES` in `models/transformations.py`.
3. For a new output, update `data/demand.json` and the product specifications in `models/products.py`.
4. Add waste rates to the relevant generator entries in `data/regions/*.json`.
