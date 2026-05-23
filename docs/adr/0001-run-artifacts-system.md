# Self-contained run artifact directories

Every `main.py` invocation writes all its outputs into a single directory under `outputs/runs/YYYY-MM-DD/<run_name>/`. We chose self-contained directories over the previous scattered layout (`outputs/baseline/`, `plots/`, ad-hoc archives) because downstream analysis, comparison, and cleanup all become trivial when a run is a single folder you can glob, copy, or delete.

## Considered options

**Scattered outputs (status quo).** Per-replication JSONs in `outputs/baseline/{scenario}/{combo}/`, MFA plots in `plots/`, comparison dashboards in `plots/scenario_comparison/`, thesis analysis in `outputs/analysis/thesis/`. Quick to browse individual plot types, but impossible to answer "what exactly did that Tuesday run produce?" without checking three locations. No config snapshot, no reproducibility record.

**Self-contained run directories (chosen).** One folder per invocation with a frozen config, structured results, captured log, and all plots. Loses the top-level `plots/` convenience, but `ls outputs/runs/2026-05-23/*/plots/mfa/` covers that. The filesystem is the index -- no database, no manifest.

**Hybrid with symlinks.** Run directory is canonical, `plots/latest/` symlinks to the most recent run's plots. Best of both, but fragile on Windows/WSL where this project runs.

## Key decisions within this design

- **A run is one `main.py` invocation**, not an individual simulation. A baseline run with 100 replications across 6 combos is one run containing 600 replications.
- **Separate result files per mode**: `run.results.grid.json` (scalar KPIs) and `run.results.baseline.json` (statistical summaries). Grid is not a degenerate baseline -- the schemas reflect genuinely different output shapes.
- **`run.config.json` is write-once.** Written at run start, never mutated. Run status lives in the results file: its presence means completion, its absence means crash or in-progress.
- **Constants get their own block** in the config, separate from scenario parameters. Constants rarely change, but when they do, old runs still document what values they used.
- **No input file hashing, no schema version.** Input parameters are fully represented in the config snapshot. Format changes are handled by the archive boundary (`outputs/_archive/`).
- **Plots separated by type**: `plots/mfa/` and `plots/comparison/` inside each run directory.
- **Per-replication files nested by scenario and combo**: `replications/{scenario}/{policy}__{strategy}/000.json`.
- **Run names are auto-generated slugs**: `{mode}_{variant}_{flags}__{HHMM}` with a `SLUG_MAP` in the naming module as the decoder ring.
- **`run_artifacts/`** is a new top-level package (naming, writer, schemas). `main.py` calls it directly.
- **Legacy outputs** (`outputs/baseline/`, `plots/`) archived to `outputs/_archive/` -- no migration attempted.

## Consequences

- Every downstream script (plotting, comparison, thesis analysis) needs to learn the new paths. The glob pattern `outputs/runs/**/run.results.*.json` replaces hardcoded paths.
- `main.py` gains artifact-writing calls at its boundaries but no new control flow.
- Print statements need cleanup (no decorative banners) since stdout is captured to `run.log`.
