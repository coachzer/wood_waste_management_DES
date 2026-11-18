# CLAUDE.md

Read `CONTEXT.md` (the domain glossary) before naming a domain concept, writing about the model, or changing simulation logic, and use its terms exactly.

## Project overview

SimPy discrete event simulation of wood waste management in Slovenia. Generators in 12 statistical regions produce EWC-coded waste, transport companies collect it, and treatment operators turn it into MDF, particle board and OSB. Monte Carlo analysis runs across `InventoryPolicy` (push/pull) × `StockStrategy` (on_demand/reorder_50/reorder_90).

## Running simulations

```bash
.venv/bin/python main.py                                        # Grid mode: 1 run per policy×strategy combo
.venv/bin/python main.py --mode baseline --replications 100     # Monte Carlo: 100 seeds per combo
.venv/bin/python main.py --mode baseline --scenario Baseline --replications 50  # Single scenario
.venv/bin/python -m analysis.paired_comparison outputs/baseline/Baseline        # Post-hoc paired (CRN) stats
```

Baseline outputs go to `outputs/baseline/{scenario}/{policy}__{strategy}/`. MFA visualizations (Plotly HTML) go to `plots/`.

**Seeding is Common Random Numbers (CRN).** Baseline replication `i` uses `seed = base_seed + i` for every policy×strategy combo, so all combos see the same waste and failure draws. `summary.csv` reports marginal per-combo CIs. `analysis/paired_comparison.py` uses the pairing (per-replication KPI differences, paired-t CIs, per-metric Holm-Bonferroni) and writes `{scenario}/paired_comparison.csv` after each baseline run.

## Known failure modes

- **Reproducibility: sort enum sets.** A given seed must yield byte-identical run JSONs across separate process invocations. Before iterating a set of `WasteType`/`OutputType` on a path that drives ordered work (collection allocation, signal creation, storage priming), `sorted(..., key=lambda e: e.value)` it and pass an ordered `List`. Keep it a `List` downstream. Enum members hash by `id()`, which `PYTHONHASHSEED` does not control, so an unsorted set of enums iterates in per-process memory order and breaks reproducibility without any error. Backstops are `tests/test_enum_set_ordering.py` and `tests/test_determinism.py`.
- **Pull policy deadlock.** Under pull, treatment must trigger collection. If treatment never requests waste, collectors stall. Check that `TreatmentOperator._order_volumes_by_waste_type()` returns orders (threshold logic is in `core/strategies/stock_strategy.py`).
- **PUSH ignores signals.** In PUSH mode, generators still emit Kanban signals but collectors ignore them and collect by volume. Under PULL, generators emit none (ADR 0032), and collectors serve treatment orders largest first (ADR 0031).
- **ABC prioritization is always on.** `BiogenicCarbonABCAnalyzer` (`core/abc_analysis.py`) feeds `TreatmentOperator._get_prioritized_transformations()`. It has no enable flag and no per-scenario setting.

## Key conventions

- **KPIs** are extracted in `analysis/baseline_aggregate.py::extract_kpis()`.
- **Units.** Waste volumes are in m³, converted from tonnes via `utils/unit_conversion.py`. Simulation time is in days, 0 to 365.
- **Seeding.** `run_single_simulation()` calls `random.seed(s)` and `np.random.seed(s)`. Per-entity RNGs come from `np.random.SeedSequence`, passed from `SimulationManager` to `FacilityBuilder` to each entity.
- **Waste types.** EWC codes are the enum values (e.g., `WasteType.CONSTRUCTION_WOOD_17_02_01 = "17 02 01"`). Transformations are keyed by `(WasteType, OutputType)`.
- **Storage overflow.** Waste above `waste_storage_capacity` goes to landfill, tracked in `WasteMonitor`. Treatment can expand storage (`EXPANSION_SIZE_M3 = 500`).
- **Region data.** One JSON per region in `data/regions/`. Generation rates are rebuilt from SURS by `data/calibrate_generation_rates.py` (ADR 0030), so do not edit them by hand. Distances come from `models/distances.py::get_distance()`.
- **Constants.** All live in `config/constants.py`. Other modules name a constant from there instead of a literal number.
- **Variable naming.** Verbose and descriptive, never abbreviated (`waste_storage_capacity`, not `wsc`).
- **No emojis** in code or comments.
- **Surgical changes.** Touch only what the task needs. For adjacent working code that could be refactored, open a ticket. If a review check fails, stop and open an issue instead of expanding scope.
- **Commits.** `type(scope): Imperative subject`, under 72 chars. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Scope is optional (a module name such as `treatment`). The subject verb says what changed and does not repeat the type. The body, after a blank line, explains *why*, not *what*. A `feat`, `fix` or `refactor` that can change simulation results needs an `Affects: <what shifted>` trailer. A commit that needs a semicolon is probably two commits. `.githooks/commit-msg` enforces this; after cloning, run `git config core.hooksPath .githooks`.

## Done means

`.venv/bin/python -m pytest` passes, including `tests/test_determinism.py` and `tests/test_enum_set_ordering.py`. The suite is slow (290 tests, about 70 s just to collect), so run it in the background.

## Ask first

- `outputs/` (Monte Carlo runs), `paper-draft/`, `.scratch/` and `HANDOFF.md` are not in git. Ask before deleting or overwriting anything in them.

## Adding new waste types or products

1. Add the enum to `models/enums.py::WasteType` (EWC format) or `OutputType`.
2. Add the efficiency/energy row to `TRANSFORMATION_CATALOGUE` and the output pathways to `WASTE_TO_OUTPUT_TYPES` in `models/transformations.py`.
3. For a new output, update `data/demand.json` and the product specifications in `models/products.py`.
4. Rerun `python -m data.calibrate_generation_rates <green-up-project dir> --write` to pick up SURS rates for the new code.
