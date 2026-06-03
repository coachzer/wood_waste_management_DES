# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project Overview

SimPy discrete event simulation of wood waste management in Slovenia. Models 12 statistical regions generating EWC-coded waste → collected by transport companies → treated into MDF, particle board, OSB. Supports Monte Carlo analysis across `InventoryPolicy` (push/pull) × `StockStrategy` (on_demand/reorder_50/reorder_90).

## Documentation Map

Each fact lives in ONE place; other docs point to it rather than restate it. Every doc has a **tense**
(present / past / future / reference) that fixes whether it may be edited to reflect new state. When in
doubt where to read or write, start here.

| Doc | Tense | Owns (single source of truth for…) |
| --- | --- | --- |
| `CLAUDE.md` (this file) | reference | architecture, conventions, failure modes, standards, this map |
| `CONTEXT.md` | reference | domain glossary (Finished Goods, PUSH/PULL, Consumption Event, …) — use these terms exactly |
| `README.md` | reference | repo entry point for a human first-timer |
| `HANDOFF.md` | **present** | **where we are now** — the ONLY current-state narrative; refreshed each session |
| `.scratch/ROADMAP.md` | **future** | **what's next** — the ONLY ordered TODO; cites issues/metrics-roadmap rather than duplicating |
| `docs/adr/*` | **past** | one decision each, at a point in time — append-only |
| `.scratch/done/*` | **past** | completed-work writeups + archived issues — append-only |
| `.scratch/metrics-roadmap.md` | reference | metric *rationale* (P1–P4) the ROADMAP draws from — not a status list |
| `.scratch/bullwhip/issues/*`, `.scratch/paper-draft-audit/*` | future | active issue specs; move to `.scratch/done/` when complete |
| `.scratch/paper-draft-audit/DATASET-README.md` | reference | the current MC dataset's KPI inventory + provenance |
| `.scratch/golden/` | **present** (live infra) | locked golden `baselines/` + `compare_baselines.py` for the freeze exit test |
| `paper-draft/` (gitignored) | future | the paper being written — consumes finished numbers, never drives code |

**Four rules that keep this readable:**

1. **Past docs are append-only.** Never edit an ADR or `done/` writeup body to match new reality. If it
   is overtaken, add a one-line `> Superseded by X` header and leave the body. (Editing a record toward an
   aspirational future is what produced the ADR 0002 done-tense landmine — see Known Failure Modes.)
2. **Current state lives in `HANDOFF.md` and nowhere else.** Other docs point to it; don't start a second
   "what's done" narrative.
3. **Next work lives in `.scratch/ROADMAP.md` and nowhere else.** It cites `metrics-roadmap.md` and the
   issue dirs for detail; those are sources, not competing TODO lists.
4. **Finished work leaves the active space.** When an issue/effort completes, move it under `.scratch/done/`
   — don't leave stale `Status:` frontmatter in a live dir. Keep any still-referenced *tooling* (e.g.
   `.scratch/golden/`) out of `done/`, since `done/` means "no longer used."

## Running Simulations

```bash
python main.py                                        # Grid mode: 1 run per policy×strategy combo
python main.py --mode baseline --replications 100     # Monte Carlo: 100 seeds per combo
python main.py --mode baseline --scenario Baseline --replications 50  # Single scenario
python monitoring/paired_comparison.py outputs/baseline/Baseline      # Post-hoc paired (CRN) stats
```

Outputs: `outputs/baseline/{scenario}/{policy}__{strategy}/`. MFA visualizations (Plotly HTML) to `plots/`.

**Seeding is Common Random Numbers (CRN)**: baseline replication `i` uses `seed = base_seed + i` reused across every policy×strategy combo, so combos face identical waste/failure draws. `summary.csv` reports marginal per-combo CIs; `monitoring/paired_comparison.py` exploits the pairing — per-replication KPI differences with paired-t CIs and a per-metric Holm-Bonferroni correction — and is auto-written as `{scenario}/paired_comparison.csv` after each baseline run (run it standalone via a file path, not `-m`, to avoid the `monitoring/__init__` circular import).

## Architecture

**Three-layer pipeline**: `WasteGenerator` → `CollectorCompany` → `TreatmentOperator` (all in `core/`). Each inherits `OperationalEntity` (`models/data_classes.py`) providing failure injection via `FailureConfig` and a three-state lifecycle: `OPERATIONAL → FAILED → RECOVERING`.

**Two entity layers**: `models/entities.py` holds data-only dataclasses (loaded from JSON). `core/*.py` holds the SimPy-active process classes that run in the simulation.

**Initialization sequence** (`SimulationManager.initialize_entities()`):

1. Reset `SimulationState._instance = None` (singleton holding all entity refs + demand tracking)
2. `FacilityDataManager.load_data()` reads `data/regions/*.json` + `data/demand.json`
3. `FacilityBuilder` creates entities per region with `UncertaintySet` + strategy enums
4. `SimulationState.initialize(generators, collectors, processors)`
5. `setup_processes()` starts monitoring + demand satisfaction checking

**Config flow**: `ScenarioConfig` → `to_uncertainty_set()` → `FacilityBuilder` → injected into every entity. Scenarios in `SCENARIO_CONFIGS` (`config/base_config.py`).

**Kanban/pull coordination**: `KanbanManager` is active in PULL mode — treatment signals collectors, collectors signal generators via kanban signals consumed in insertion order (no priority weighting; the half-wired signal `priority` field was removed — the deferred urgency-aware variant is recorded in `.scratch/metrics-roadmap.md`). In PUSH mode, generators emit signals but collectors ignore them (collection is volume-driven).

**ABC prioritization**: `BiogenicCarbonABCAnalyzer` (`core/abc_analysis.py`) ranks products by biogenic carbon stock impact into A/B/C classes (priority weights 1.0/0.7/0.4). Always on — there is no enable flag; `TreatmentOperator` initializes the priority map unconditionally. Used in `_get_prioritized_transformations()` with a 2.0× scoring multiplier, alongside a finished-goods shortfall term (`max(0, capacity - current) / capacity` per output type) that steers production toward the most depleted buffer. Not configurable per scenario. Data source: `data/demand.json` + `models/products.py`.

## Known Failure Modes

- **Singleton reset**: `SimulationState._instance = None` in `SimulationManager.__init__()` gives each run fresh state. Stale entity references mean this reset was skipped.
- **Pull policy deadlock**: Pull requires treatment to trigger collection; if treatment never requests waste, collectors stall. Verify `TreatmentOperator.demand` is set via `_apply_stock_strategy_to_demand_calculation()`.
- **Unused artifact**: The standalone-generated `demand_with_abc.json` at repo root is NOT consumed by the simulation — don't wire logic to it.
- **KPIs**: Extracted via `monitoring/baseline_aggregate.py::extract_kpis()` from monitor history dicts.

## Key Conventions

- **Units**: Waste volumes in m³ (converted from tonnes via `utils/unit_conversion.py`). Simulation time in days (0–365).
- **Seeding**: `random.seed(s)` + `np.random.seed(s)` in `run_single_simulation()`. Per-entity RNGs seeded via `np.random.SeedSequence` propagated `SimulationManager` → `FacilityBuilder` → each entity (deterministic child seed). Results are reproducible across separate process invocations: a given seed yields byte-identical run JSONs run-to-run. This holds only because every iteration of a `set` of `WasteType`/`OutputType` members on a simulation-affecting path is `sorted(..., key=lambda e: e.value)` — enum members hash by `id()`, which `PYTHONHASHSEED` does not control, so an unsorted set-of-enums iterates in per-process memory order and silently breaks reproducibility. When iterating a set of enums on any path that drives ordered work (collection allocation, signal creation, storage priming), always sort by `.value` first; pass the result as an ordered `List`, never re-wrap it in a `set`.
- **Waste types**: EWC codes as enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations keyed by `(WasteType, OutputType)`.
- **Storage overflow**: Exceeding `waste_storage_capacity` → landfill, tracked in `WasteMonitor`. Treatment can expand (`EXPANSION_SIZE_M3 = 500`).
- **Region data**: One JSON per region in `data/regions/`. Distances via `models/distances.py::get_distance()`.
- **Constants**: All in `config/constants.py` — no magic numbers elsewhere.
- **Variable naming**: Verbose and descriptive, never abbreviated (`waste_storage_capacity` not `wsc`).
- **No emojis** in code or comments.

## Adding New Waste Types or Products

1. Add enum to `models/enums.py::WasteType` (EWC format) or `OutputType`
2. Add transformation in `FacilityBuilder._get_base_transformations()` and `_get_appropriate_mappings()`
3. Update `data/demand.json` and `SimulationState` product dicts if new output
4. Add waste rates to relevant `data/regions/*.json` generator entries

## Standards

**Simplicity first**: reject unnecessary abstractions, premature optimization, and "clever" code. One straightforward solution beats several flexible options.

**No speculative features**: implement only what's asked. No "while we're here" additions, no "might be useful later" code, no config options "just in case".

**Surgical changes**: touch only what you must. Don't refactor adjacent code that isn't broken — open a ticket instead. If a review check fails, stop and open an issue rather than expanding scope.

**Explicit over implicit**: no magic numbers (use `constants.py`), document every parameter. Docstrings on all public methods; inline comments only when the *why* isn't obvious.

**Commits**: imperative mood, under 72 chars, no colon after the verb (`Add`, `Fix`, `Refactor`, `Update`, `Remove`, `Improve`). Body (after a blank line) explains *why*, not *what*. If a commit needs a semicolon, it's probably two commits.

## Agent Skills

Invoked via `/skill-name`.

| Skill | Purpose |
| --- | --- |
| `/diagnose` | Structured debugging |
| `/grill-with-docs` | Stress-test a plan against the domain model; updates `CONTEXT.md` |
| `/tdd` | Red-green-refactor loop |
| `/to-issues` | Break a plan into grabbable issues |
| `/triage` | Issue triage state machine |
| `/handoff` | Compact context for agent handoffs |