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

**Kanban/pull coordination**: `KanbanManager` is active in PULL mode — treatment signals collectors, collectors signal generators via kanban signals with priority weighting. In PUSH mode, generators emit signals but collectors ignore them (collection is volume-driven instead).

## Key Conventions

- **Units**: Waste volumes in m³ (converted from tonnes via `utils/unit_conversion.py`). Simulation time in days (0–365).
- **Seeding**: `random.seed(s)` + `np.random.seed(s)` in `run_single_simulation()`. Per-entity RNGs are seeded via `np.random.SeedSequence` propagated through `SimulationManager` → `FacilityBuilder` → each entity gets a deterministic child seed.
- **Waste types**: EWC codes as enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations keyed by `(WasteType, OutputType)`.
- **Storage overflow**: Exceeding `waste_storage_capacity` → landfill, tracked in `WasteMonitor`. Treatment can dynamically expand (`EXPANSION_SIZE_M3 = 500`).
- **Region data**: One JSON per region in `data/regions/`. Distances via `models/distances.py::get_distance()`.
- **Constants**: All in `config/constants.py` — simulation duration, emission factors, density, and entity behavior constants (failure efficiency, collection ratios, buffer thresholds).

## Adding New Waste Types or Products

1. Add enum to `models/enums.py::WasteType` (EWC format) or `OutputType`
2. Add transformation in `FacilityBuilder._get_base_transformations()` and `_get_appropriate_mappings()`
3. Update `data/demand.json` and `SimulationState` product dicts if new output
4. Add waste rates to relevant `data/regions/*.json` generator entries

## Debugging

- **Singleton reset**: `SimulationState._instance = None` in `SimulationManager.__init__()` — each run gets fresh state. Stale entity references mean this reset was skipped.
- **Pull policy deadlock**: Pull requires treatment to trigger collection; if treatment never requests waste, collectors stall. Verify `TreatmentOperator.demand` is set via `_apply_stock_strategy_to_demand_calculation()`.
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

## Development Rules

- **Variable naming** - Never use short-form or abbreviated variable names. All variables must be verbose and descriptive so their purpose is clear at first glance (e.g., `waste_storage_capacity` not `wsc`, `treatment_operator` not `tOp`).
- **No emojis** - No emojis in code or comments. Docs only sparingly to highlight important features.

## Design Principles

1. **Modularity**: each module has one job
2. **Domain-Driven Design**: use real-world terms (Roundwood, Facility, Product)
3. **Painfully Explicit Specs**: no magic numbers (use `constants.py`), document every parameter
4. **Excessive Documentation**: add docstrings, update docs when changing behavior

## Working Style

- **Think before coding**: state assumptions explicitly. Ask rather than guess. Push back when a simpler approach exists. Stop when confused.
- **Surgical changes**: touch only what you must. Don't improve adjacent code. Match existing style. Don't refactor what isn't broken.
- **Goal-driven execution**: define success criteria. Loop until verified. Strong success criteria let Claude loop independently.

## Agent Skills

### Issue tracker

Issues tracked as local markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (one CONTEXT.md + docs/adr/ at repo root). See `docs/agents/domain.md`.

## Available Skills (global, loaded on demand via `/skill-name`)

| Skill | Purpose |
| --- | --- |
| `/diagnose` | Structured debugging: reproduce, minimise, hypothesise, instrument, fix |
| `/grill-with-docs` | Stress-test a plan against domain model, updates CONTEXT.md and ADRs |
| `/grill-me` | Relentless interview about a plan or design until shared understanding |
| `/tdd` | Red-green-refactor test-driven development loop |
| `/improve-codebase-architecture` | Find refactoring and design improvement opportunities |
| `/prototype` | Build throwaway prototypes (terminal app or UI variations) |
| `/to-issues` | Break a plan/spec into independently-grabbable issues |
| `/to-prd` | Convert conversation context into a PRD |
| `/triage` | Issue triage via state machine workflow |
| `/zoom-out` | Get broader architectural perspective on unfamiliar code |
| `/caveman` | Ultra-compressed communication (~75% token reduction) |
| `/handoff` | Compact conversation context for agent handoffs |
| `/write-a-skill` | Create new agent skills |
| `/setup-matt-pocock-skills` | Configure repo issue tracker, triage labels, domain docs |

## Commit Convention

Use imperative mood, under 72 characters. Format:

```text
<Verb> <what changed>

<why, if non-obvious>
```

Verbs: `Add`, `Fix`, `Refactor`, `Update`, `Remove`, `Improve`. No colons after the verb. If a commit needs a semicolon, it should probably be two commits. The body (separated by a blank line) explains *why*, not *what* -- use it for non-trivial logic changes.
