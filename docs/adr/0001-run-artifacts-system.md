# Self-contained run artifact directories

> NOTE (2026-09-28): this design was never implemented. No code writes to `outputs/runs/`. Baseline runs
> still write to `outputs/baseline/{scenario}/{policy}__{strategy}/`, and grid mode writes to `plots/`.
> Plans 009-011 (`plans/README.md`) carry a revised version of this layout, with a manifest and a
> `kpis.csv`, and are still TODO. Treat this ADR as accepted but not implemented. The body keeps its
> original meaning under the append-only doc rule.

Every `main.py` invocation writes all its outputs into a single directory under `outputs/runs/YYYY-MM-DD/<run_name>/`. We chose self-contained directories over the previous scattered layout (`outputs/baseline/`, `plots/`, ad-hoc archives) because a run that is a single folder can be globbed, copied or deleted in one step, which makes downstream analysis, comparison and cleanup simple.

## Considered options

**Scattered outputs (status quo).** Per-replication JSONs in `outputs/baseline/{scenario}/{combo}/`, MFA plots in `plots/`, comparison dashboards in `plots/scenario_comparison/`, thesis analysis in `outputs/analysis/thesis/`. Individual plot types are quick to browse, but answering "what exactly did that Tuesday run produce?" means checking three locations. There is no config snapshot and no reproducibility record.

**Self-contained run directories (chosen).** One folder per invocation with a frozen config, structured results, captured log and all plots. The top-level `plots/` shortcut goes away, but `ls outputs/runs/2026-05-23/*/plots/mfa/` replaces it. The filesystem is the index. There is no database and no manifest.

**Hybrid with symlinks.** The run directory is canonical, and `plots/latest/` symlinks to the most recent run's plots. This keeps both layouts, but symlinks are fragile on Windows/WSL, where this project runs.

## Key decisions within this design

- **A run is one `main.py` invocation**, not an individual simulation. A baseline run with 100 replications across 6 combos is one run containing 600 replications.
- **Each mode has its own result file.** `run.results.grid.json` holds scalar KPIs and `run.results.baseline.json` holds statistical summaries. Grid is not a degenerate baseline, and the two schemas reflect different output shapes.
- **`run.config.json` is write-once.** It is written at run start and never changed. Run status lives in the results file. If the file exists, the run completed. If it is missing, the run crashed or is still running.
- **Constants get their own block** in the config, separate from scenario parameters. Constants rarely change, but when they do, old runs still record the values they used.
- **No input file hashing, no schema version.** The config snapshot records every input parameter. The archive boundary (`outputs/_archive/`) handles format changes.
- **Plots are separated by type** into `plots/mfa/` and `plots/comparison/` inside each run directory.
- **Per-replication files are nested by scenario and combo**: `replications/{scenario}/{policy}__{strategy}/000.json`.
- **Run names are auto-generated slugs** of the form `{mode}_{variant}_{flags}__{HHMM}`. A `SLUG_MAP` in the naming module decodes them.
- **`run_artifacts/`** is a new top-level package (naming, writer, schemas) that `main.py` calls directly.
- **Legacy outputs** (`outputs/baseline/`, `plots/`) move to `outputs/_archive/` with no migration.

## Consequences

- Every downstream script (plotting, comparison, thesis analysis) must switch to the new paths. The glob `outputs/runs/**/run.results.*.json` replaces hardcoded paths.
- `main.py` gains artifact-writing calls at its start and end but no new control flow.
- Print statements need cleanup (no decorative banners), since stdout is captured to `run.log`.
