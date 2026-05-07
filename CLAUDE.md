# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SimPy-based discrete event simulation of wood waste management in Slovenia. Models 12 statistical regions generating waste (EWC-coded) → collected by transport companies → treated into MDF, particle board, OSB. Supports Monte Carlo analysis across `InventoryPolicy` (push/pull) × `StockStrategy` (on_demand/reorder_50/reorder_90) combinations.

## Running Simulations

```bash
python main.py                                        # Grid mode: 1 run per policy×strategy combo
python main.py --mode baseline --replications 100     # Monte Carlo: 100 seeds per combo
python main.py --mode baseline --scenario Baseline --replications 50  # Single scenario
```

Outputs: `outputs/baseline/{scenario}/{policy}__{strategy}/`. MFA visualizations (Plotly HTML) to `plots/`.

Post-processing Monte Carlo results:

```bash
python tools/merge_and_plot_summaries.py <path-to-baseline-output>
```

## Architecture

**Three-layer pipeline**: `WasteGenerator` → `CollectorCompany` → `TreatmentOperator` (all in `core/`). Each inherits `OperationalEntity` (`models/data_classes.py`) providing failure injection via `FailureConfig` and a three-state lifecycle: `OPERATIONAL → FAILED → RECOVERING`.

**Two entity layers**: `models/entities.py` has data-only dataclasses (loaded from JSON). `core/*.py` has the SimPy-active process classes that run in the simulation.

**Initialization sequence** (in `SimulationManager.initialize_entities()`):

1. Reset `SimulationState._instance = None` (singleton holding all entity refs + demand tracking)
2. `FacilityDataManager.load_data()` reads `data/regions/*.json` + `data/demand.json`
3. `FacilityBuilder` creates entities per region with `UncertaintySet` + strategy enums
4. `SimulationState.initialize(generators, collectors, processors)`
5. `setup_processes()` starts monitoring + demand satisfaction checking

**Config flow**: `ScenarioConfig` → `to_uncertainty_set()` → `FacilityBuilder` → injected into every entity. Scenarios defined in `SCENARIO_CONFIGS` dict in `config/base_config.py`.

**Kanban/pull coordination**: `KanbanManager` is wired into all entities but not actively driving behavior in the current simplified approach.

## Key Conventions

- **Units**: Waste volumes in m³ (converted from tonnes via `utils/unit_conversion.py`). Simulation time in days (0–365).
- **Seeding**: `random.seed(s)` + `np.random.seed(s)` in `run_single_simulation()`. Entities also use `np.random.default_rng(42)` for failure checks.
- **Waste types**: EWC codes as enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations keyed by `(WasteType, OutputType)`.
- **Storage overflow**: Exceeding `waste_storage_capacity` → landfill, tracked in `WasteMonitor`. Treatment can dynamically expand (`EXPANSION_SIZE_M3 = 500`).
- **Region data**: One JSON per region in `data/regions/`. Distances via `models/distances.py::get_distance()`.
- **Constants**: All in `config/constants.py` (simulation duration, emission factors, density).
- **Tests**: `tests/` structure exists but test files are minimal. Validate with deterministic grid runs.

## Adding New Waste Types or Products

1. Add enum to `models/enums.py::WasteType` (EWC format) or `OutputType`
2. Add transformation in `FacilityBuilder._get_base_transformations()` and `_get_appropriate_mappings()`
3. Update `data/demand.json` and `SimulationState` product dicts if new output
4. Add waste rates to relevant `data/regions/*.json` generator entries

## Debugging

- **Singleton reset**: `SimulationState._instance = None` in `SimulationManager.__init__()` — each run gets fresh state. Stale entity references mean this reset was skipped.
- **Pull policy deadlock**: Pull requires treatment to trigger collection; if treatment never requests waste, collectors stall. Verify `TreatmentOperator.demand` is set via `_distribute_demand()`.
- **KPIs**: Extracted via `monitoring/baseline_aggregate.py::extract_kpis()` from monitor history dicts.

## Code Review Standards

The orchestrator reviews all sub-agent code against these criteria:

### Simplicity First

- Reject unnecessary abstractions
- Reject premature optimization
- Reject "clever" code that sacrifices readability
- One straightforward solution is better than multiple "flexible" options

### No Speculative Features

- Only implement what's explicitly required
- No "while we're here" additions
- No "this might be useful later" code
- No extra configuration options "just in case"

### Standard Patterns

- Follow existing codebase patterns (see Architecture section above)
- New patterns require explicit justification with measurable benefit
- When in doubt, use the boring solution

### Review Checklist

- [ ] Does exactly what was asked, nothing more
- [ ] No new dependencies without justification
- [ ] No commented-out code or TODOs without tickets
- [ ] Error handling matches existing patterns
- [ ] Tests cover the new code paths

## Dependency Management

Use `addBlockedBy` to express task relationships:

- Task A: Define schema types
- Task B: Implement service (blocked by A)
- Task C: Write tests (blocked by B)
- Task D: Update documentation (blocked by B)

Tasks B, C, D can be spawned in parallel - the dependency system handles ordering.

## PRD Treatment

- Treat as starting point, not immutable spec
- Flag contradictions or ambiguities immediately
- Propose amendments with technical rationale
- Document deviations in task descriptions

## Orchestrator Responsibilities

1. **Decompose** requirements into bounded tasks
2. **Delegate** to sub-agents with explicit scope
3. **Review** all sub-agent output before integration
4. **Reject** work that doesn't meet standards (with specific feedback)
5. **Integrate** approved work and update task status

## Development Rules

- **Variable naming** - Never use short-form or abbreviated variable names. All variables must be verbose and descriptive so their purpose is clear at first glance (e.g., `waste_storage_capacity` not `wsc`, `treatment_operator` not `tOp`).
- **No emojis** - No emojis in code or comments. Docs only sparingly to highlight important features.
