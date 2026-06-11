# CLAUDE.md

Guidance for Claude Code working in this repository. Domain glossary: see @CONTEXT.md — use those terms exactly.

## Project Overview

SimPy discrete event simulation of wood waste management in Slovenia. Models 12 statistical regions generating EWC-coded waste → collected by transport companies → treated into MDF, particle board, OSB. Supports Monte Carlo analysis across `InventoryPolicy` (push/pull) × `StockStrategy` (on_demand/reorder_50/reorder_90).

## Running Simulations

```bash
python main.py                                        # Grid mode: 1 run per policy×strategy combo
python main.py --mode baseline --replications 100     # Monte Carlo: 100 seeds per combo
python main.py --mode baseline --scenario Baseline --replications 50  # Single scenario
python -m analysis.paired_comparison outputs/baseline/Baseline        # Post-hoc paired (CRN) stats
```

Outputs: `outputs/baseline/{scenario}/{policy}__{strategy}/`. MFA visualizations (Plotly HTML) to `plots/`.

**Seeding is Common Random Numbers (CRN)**: baseline replication `i` uses `seed = base_seed + i` reused across every policy×strategy combo, so combos face identical waste/failure draws. `summary.csv` reports marginal per-combo CIs; `analysis/paired_comparison.py` exploits the pairing (per-replication KPI differences, paired-t CIs, per-metric Holm-Bonferroni) and auto-writes `{scenario}/paired_comparison.csv` after each baseline run.

## Architecture

**Three-layer pipeline**: `WasteGenerator` → `CollectorCompany` → `TreatmentOperator` (all in `core/`). Each inherits `OperationalEntity` (`models/data_classes.py`) providing failure injection via `FailureConfig` and a three-state lifecycle: `OPERATIONAL → FAILED → RECOVERING`.

**Two entity layers**: `models/entities.py` holds data-only dataclasses (loaded from JSON). `core/*.py` holds the SimPy-active process classes that run in the simulation. Construction: `SimulationManager.initialize_entities()` → `FacilityDataManager.load_data()` → `FacilityBuilder` (config injected as `ScenarioConfig` → `to_uncertainty_set()`) → `SimulationState.initialize()`. Scenarios in `SCENARIO_CONFIGS` (`config/base_config.py`).

**Kanban/pull coordination**: `KanbanManager` is active in PULL mode — treatment signals collectors, collectors signal generators; signals are consumed in insertion order (no priority weighting). In PUSH mode, generators emit signals but collectors ignore them (collection is volume-driven).

**ABC prioritization**: `BiogenicCarbonABCAnalyzer` (`core/abc_analysis.py`) ranks products into A/B/C classes (priority weights 1.0/0.7/0.4) used in `TreatmentOperator._get_prioritized_transformations()`. Always on — no enable flag, not configurable per scenario. Data: `data/demand.json` + `models/products.py`.

## Known Failure Modes

- **Reproducibility — YOU MUST sort enum sets.** A given seed must yield byte-identical run JSONs across separate process invocations. **YOU MUST `sorted(..., key=lambda e: e.value)` any set of `WasteType`/`OutputType` before iterating on a path that drives ordered work** (collection allocation, signal creation, storage priming); pass an ordered `List`, never re-wrap in a `set`. (Enum members hash by `id()`, which `PYTHONHASHSEED` does not control, so an unsorted set-of-enums iterates in per-process memory order and silently breaks reproducibility.) Backstops: `tests/test_enum_set_ordering.py`, `tests/test_determinism.py`.
- **Singleton reset**: `SimulationState._instance = None` in `SimulationManager.__init__()` gives each run fresh state. Stale entity references mean this reset was skipped.
- **Pull policy deadlock**: Pull requires treatment to trigger collection; if treatment never requests waste, collectors stall. Verify `TreatmentOperator.demand` is set via `_apply_stock_strategy_to_demand_calculation()`.
- **Unused artifact**: The standalone-generated `demand_with_abc.json` at repo root is NOT consumed by the simulation — don't wire logic to it.
- **KPIs**: Extracted via `analysis/baseline_aggregate.py::extract_kpis()` from monitor history dicts.

## Key Conventions

- **Units**: Waste volumes in m³ (converted from tonnes via `utils/unit_conversion.py`). Simulation time in days (0–365).
- **Seeding**: `random.seed(s)` + `np.random.seed(s)` in `run_single_simulation()`. Per-entity RNGs seeded via `np.random.SeedSequence` propagated `SimulationManager` → `FacilityBuilder` → each entity.
- **Waste types**: EWC codes as enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations keyed by `(WasteType, OutputType)`.
- **Storage overflow**: Exceeding `waste_storage_capacity` → landfill, tracked in `WasteMonitor`. Treatment can expand (`EXPANSION_SIZE_M3 = 500`).
- **Region data**: One JSON per region in `data/regions/`. Distances via `models/distances.py::get_distance()`.
- **Constants**: All in `config/constants.py` — no magic numbers elsewhere.
- **Variable naming**: Verbose and descriptive, never abbreviated (`waste_storage_capacity` not `wsc`).
- **No emojis** in code or comments.
- **Surgical changes**: touch only what you must; don't refactor adjacent working code — open a ticket. If a review check fails, stop and open an issue rather than expanding scope.
- **Commits**: imperative mood, under 72 chars, no colon after the verb (`Add`, `Fix`, `Refactor`, `Update`, `Remove`, `Improve`). Body (after a blank line) explains *why*, not *what*. If a commit needs a semicolon, it's probably two commits.

## Adding New Waste Types or Products

1. Add enum to `models/enums.py::WasteType` (EWC format) or `OutputType`
2. Add transformation in `FacilityBuilder._get_base_transformations()` and `_get_appropriate_mappings()`
3. Update `data/demand.json` and `SimulationState` product dicts if new output
4. Add waste rates to relevant `data/regions/*.json` generator entries

## Docs & Skills

Each fact lives in ONE doc; others point to it. Past decisions → `docs/adr/*` and `.scratch/done/*` (append-only — never edit a record to match new reality; add a `> Superseded by X` header and leave the body). Domain glossary is imported at the top (@CONTEXT.md).

Skills (invoke via `/name`): `/diagnose` (structured debugging), `/grill-with-docs` (stress-test a plan against the domain model; updates `CONTEXT.md`), `/tdd` (red-green-refactor), `/to-issues` (break a plan into grabbable issues), `/triage` (issue triage), `/handoff` (compact context for handoffs).
