# Plan 011: Cross-run comparison CLI reading kpis.csv and manifests

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 566a59e..HEAD -- analysis/ visualization/ config/paths.py main.py`
> Plans 009 AND 010 must be DONE first — this plan consumes `RunPaths.locate`,
> `manifest.json`, `kpis.csv`, and `KPI_SCHEMA_VERSION`, none of which exist
> before them. Expect diffs from 009/010; anything beyond their scope, report.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (pure read-side addition; touches no simulation or
  existing-artifact code path)
- **Depends on**: plans/009-run-paths-module-and-manifest.md,
  plans/010-baseline-mode-run-directories.md
- **Category**: tooling (output reorganization, phase 3 of 3)
- **Planned at**: commit `566a59e`, 2026-06-11

## Why this matters

Every analysis tool in the repo compares policy×strategy combos *within* one
run. There is no tool that compares *across* runs — e.g. "did plan 004 move
the landfill KPI?", "Baseline vs SupplyDisruption service levels", or "the
100-replication refresh vs the paper's frozen numbers". Today that means
hand-opening two `summary.csv` trees. After this plan:

```bash
python -m analysis.compare_runs baseline_Baseline_n50__1432 LATEST
```

reads each run's `kpis.csv` + `manifest.json`, writes a tidy
`comparison.csv` plus one grouped-bar CI figure per metric, prints the
provenance diff (git SHA, config deltas), and — when the manifests show the
runs are CRN-pairable — adds paired per-replication difference statistics.

## Current state

Facts the executor needs (verify against the live post-010 code; the plan was
written against `566a59e` plus plans 009/010 as specified):

- **`kpis.csv`** (written by plan 010, `analysis/kpi_table.py`): header
  `scenario,inventory_policy,stock_strategy,replication,seed,metric,value`,
  one row per (replication, metric), nested KPI namespaces dot-flattened
  (e.g. `bullwhip.treatment_anchored`). Lives at `{run_dir}/kpis.csv`.
- **`manifest.json`** (plan 010, step 6): keys include `run_name`,
  `created_at`, `mode`, `replications`, `base_seed`, `scenario_filter`,
  `scenarios` (name → ScenarioConfig dict), `kpi_schema_version`, `git_sha`,
  `git_dirty`.
- **`RunPaths.locate(ref)`** (plan 009, `config/paths.py`): resolves a run
  reference — an existing path, a slug under the runs root, or `None`/
  `"LATEST"` via the LATEST pointer — to a `RunPaths`; raises
  `FileNotFoundError` with a listing of available slugs when it cannot.
- **CRN seeding** (CLAUDE.md): replication `i` uses `seed = base_seed + i`
  for every combo. Two runs are pairable on a KPI iff they share `base_seed`,
  `replications`, and the (scenario, policy, strategy) cell exists in both —
  then replication index `i` faced identical draws in both runs.
- **Existing paired-stats exemplar**: `analysis/paired_comparison.py` —
  `_mean(values)`, `_stdev(values)`, and `_paired_t_ci(differences, alpha)`
  (returns `(mean_diff, ci_low, ci_high)` using scipy's t quantile). Reuse
  the module's public helpers if importable without side effects; otherwise
  replicate the small t-CI computation locally (scipy is a declared dep).
- **Figure conventions exemplar**: `visualization/kpi_family_figures.py` —
  `matplotlib.use("Agg")` at module top before pyplot import; grouped bars
  with CI whiskers; PDF metadata pinned for byte-stability:

  ```python
  fig.savefig(
      output_path,
      metadata={"CreationDate": datetime.datetime(1970, 1, 1), "ModDate": datetime.datetime(1970, 1, 1)},
  )
  ```

- **Test exemplar**: `tests/monitoring/test_kpi_family_figures.py` and the
  fixtures in `tests/monitoring/conftest.py` fabricate run trees under
  `tmp_path`; follow that style (no real simulations in tests).
- **CLI exemplar**: the `__main__` block of `analysis/paired_comparison.py`
  (argparse, module runnable via `python -m`).
- Repo conventions: verbose variable names, no emojis, constants in
  `config/constants.py`, no magic numbers, surgical changes.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass |
| Two tiny real runs for an end-to-end check | `/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --out-root /tmp/cmp_runs` (run twice) | two slug dirs under /tmp/cmp_runs |
| The new CLI | `/mnt/c/Python313/python.exe -m analysis.compare_runs <refA> <refB> --runs-root /tmp/cmp_runs` | comparison dir written, summary printed |

## Scope

**In scope** (the only files to create/modify):
- `analysis/compare_runs.py` (create)
- `config/constants.py` (add ONE constant: `RUN_COMPARISONS_DIRNAME = "comparisons"`)
- `tests/monitoring/test_compare_runs.py` (create)
- `CLAUDE.md` (one line in Running Simulations), `plans/README.md` (status)

**Out of scope** (do NOT touch):
- `main.py`, `config/paths.py`, `analysis/kpi_table.py`,
  `analysis/paired_comparison.py` and every other existing analysis /
  visualization module (read and import them; never edit them).
- The legacy `outputs/baseline/` tree — this tool reads new-style runs only;
  legacy runs have no `kpis.csv`/`manifest.json` and the correct behavior is
  the clear `FileNotFoundError` explaining that, not a compatibility shim.
- Cross-SCENARIO statistics within one run (that is `paired_comparison.py`'s
  job); this tool compares the SAME cell across DIFFERENT runs.

## Git workflow

- Branch: `advisor/011-cross-run-comparison`
- Imperative commits <72 chars, no colon, no Co-Authored-By. Do NOT push.

## Steps

### Step 1: Add the output-location constant

In `config/constants.py`, after `RUNS_ROOT` (added by plan 009), add:

```python
RUN_COMPARISONS_DIRNAME = "comparisons"  # {RUNS_ROOT}/comparisons/{slugA}__vs__{slugB}/
```

**Verify**: `/mnt/c/Python313/python.exe -c "from config.constants import RUN_COMPARISONS_DIRNAME; print(RUN_COMPARISONS_DIRNAME)"` → `comparisons`

### Step 2: Create `analysis/compare_runs.py` — loading and pairing logic

Module layout (pure functions first, I/O last, mirroring
`analysis/paired_comparison.py`):

```python
"""Compare KPI distributions across two or more baseline runs.

Reads each run's kpis.csv (tidy long format) and manifest.json, writes a
comparison.csv plus one grouped-bar CI figure per metric under
{runs_root}/comparisons/{slugA}__vs__{slugB}/, and prints the provenance
diff. When manifests share base_seed and replications, per-replication
paired differences (CRN pairing on replication index) are reported for
run pairs; otherwise comparison is unpaired marginals only.
"""
```

Functions to implement:

1. `load_run(run_paths) -> dict` — returns
   `{"name": ..., "manifest": <parsed json>, "rows": <list of dicts>}` where
   rows come from `csv.DictReader` over `kpis.csv` with `value` cast to
   `float` (empty string → skip the row), `replication` to `int`. Raise
   `FileNotFoundError` naming the missing file if either `kpis.csv` or
   `manifest.json` is absent (this is how legacy trees fail cleanly).
2. `check_schema_versions(loaded_runs) -> list[str]` — returns warning
   strings when `kpi_schema_version` differs between runs; the CLI prints
   them prefixed `WARNING:` and continues on the **intersection** of metric
   names (a missing metric in one run must not crash the comparison).
3. `runs_are_pairable(manifest_a, manifest_b) -> bool` — True iff
   `base_seed` and `replications` are present and equal in both.
4. `marginal_stats(rows) -> dict[(scenario, policy, strategy, metric), (mean, ci_low, ci_high, n)]`
   — group rows by cell+metric; mean and a 95% t-interval over replication
   values (same alpha-0.05 t-CI math as `summary_rows` in
   `analysis/baseline_aggregate.py:71` — read it and match the formula).
5. `paired_differences(rows_a, rows_b) -> dict[(scenario, policy, strategy, metric), (mean_diff, ci_low, ci_high, n)]`
   — join on (scenario, policy, strategy, metric, replication), compute B−A
   per replication, then the paired-t CI. Cells present in only one run are
   skipped (collect their keys into a warnings list, do not crash).

All dict iteration that drives output ordering must be over `sorted(...)`
keys — output files must be deterministic (repo determinism convention).

**Verify**: `/mnt/c/Python313/python.exe -c "import analysis.compare_runs"` → no output, exit 0.

### Step 3: Writers — comparison.csv and per-metric figures

In the same module:

1. `comparison_rows(loaded_runs, stats_per_run, paired) -> list[str]` —
   header
   `scenario,inventory_policy,stock_strategy,metric,run_name,mean,ci95_low,ci95_high,count,paired_diff_vs_first,paired_ci95_low,paired_ci95_high`
   — one row per (cell, metric, run); the three paired columns are filled
   only on non-first runs when pairable, else empty strings.
2. `write_comparison_figures(output_dir, loaded_runs, stats_per_run, metrics) -> list[Path]`
   — for each metric in `metrics`: grouped bar chart, x groups = the six
   combos (label `{policy}\n{strategy}`), one bar per run with the run slug
   in the legend, CI whiskers via `yerr`. Follow
   `visualization/kpi_family_figures.py` exactly for: `matplotlib.use("Agg")`
   before pyplot import, figure sizing, and the 1970 PDF `metadata` (excerpt
   in Current state). Filename: `{metric}.pdf` with dots replaced by `_`
   (e.g. `bullwhip_treatment_anchored.pdf`). When a run lacks the metric,
   draw its bars at 0 with a hatched pattern and note it in the axis title.
3. Default metric list (a module constant, defined in THIS module since it
   is presentation choice, not a simulation constant):

   ```python
   DEFAULT_COMPARISON_METRICS = (
       "service_level_full_pct",
       "total_emissions_kgco2e",
       "total_system_cost",
       "landfill_volume_m3",
   )
   ```

   (Confirm these four exact key names against `_SUMMARY_METRICS` in
   `analysis/baseline_aggregate.py` before hardcoding — if a name differs,
   use the name found there.)

**Verify**: step 5's tests cover these; for now
`/mnt/c/Python313/python.exe -c "from analysis.compare_runs import DEFAULT_COMPARISON_METRICS, comparison_rows; print(len(DEFAULT_COMPARISON_METRICS))"` → `4`.

### Step 4: CLI

`__main__` block (argparse, modeled on `analysis/paired_comparison.py`):

- Positional: `run_refs`, `nargs="+"` — at least 2 (enforce with a clear
  parser error). Each resolved via `RunPaths.locate(ref, runs_root=...)`;
  the literal string `LATEST` (any case) resolves like `None`.
- `--runs-root` (default `None` → `RUNS_ROOT` from constants, matching
  `RunPaths` defaults), `--metrics` (`nargs="+"`, default
  `DEFAULT_COMPARISON_METRICS`; the special value `all` means every metric in
  the intersection), `--out` (default `None` →
  `{runs_root}/comparisons/{slugA}__vs__{slugB}[__vs__...]/`).
- Flow: locate → load → schema warnings → marginal stats per run → if
  exactly pairwise-pairable with the first run, paired diffs vs first →
  write `comparison.csv` → write figures → print to stdout: each run's
  `run_name`, `created_at`, `git_sha`(+` (dirty)` when `git_dirty`),
  `base_seed`, `replications`; whether pairing applied; a config diff — for
  scenarios present in both manifests, every ScenarioConfig field whose
  value differs, as `scenario.field: A_value -> B_value` (plain dict
  comparison, fields are flat after `dataclasses.asdict`); and the output
  directory path.
- Exit nonzero only on locate/load failure; statistical content never
  changes the exit code.

**Verify** (end-to-end, needs two real mini-runs):

```bash
/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --out-root /tmp/cmp_runs
/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --out-root /tmp/cmp_runs
/mnt/c/Python313/python.exe -m analysis.compare_runs $(ls /tmp/cmp_runs | grep -v LATEST | head -1) LATEST --runs-root /tmp/cmp_runs
```

Expected: stdout shows both runs' provenance, "paired: yes" (same base_seed
and replications), zero-ish paired diffs (identical seeds → identical KPIs);
the comparison dir contains `comparison.csv` + 4 PDFs.

### Step 5: Tests

Create `tests/monitoring/test_compare_runs.py`. Fabricate two fake run trees
under `tmp_path` (helper writing `manifest.json` + `kpis.csv` directly — do
NOT run simulations). Cover at least:

1. `runs_are_pairable` true/false on base_seed and replications mismatches.
2. `paired_differences` on hand-computed values (e.g. run B = run A + 1.0 on
   every replication → mean_diff exactly 1.0, CI width 0 → degenerate CI
   handling must not divide by zero; mirror how
   `analysis/paired_comparison.py` guards zero-variance differences — read
   it and match).
3. Metric-intersection behavior: a metric present only in run A produces a
   warning and is dropped, no exception.
4. `comparison_rows` header exactness and deterministic row order (two calls,
   identical output).
5. CLI smoke via `load_run`+writers composed directly (not subprocess):
   output dir contains `comparison.csv` and one PDF per default metric
   (monkeypatch metrics list to 1 to keep the test fast).
6. `load_run` on a directory missing `kpis.csv` raises `FileNotFoundError`
   mentioning the filename (the legacy-tree failure mode).

Red/blue verify per repo convention: mutate one assertion to red, confirm it
fails, restore — note this in your report.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/monitoring/test_compare_runs.py -q` → all pass; then full suite.

### Step 6: Documentation

In `CLAUDE.md` "Running Simulations" code block, add one line:

```bash
python -m analysis.compare_runs <run> <run>   # Cross-run KPI comparison (LATEST works as a ref)
```

Update the status row in `plans/README.md`.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass.

## Test plan

All in `tests/monitoring/test_compare_runs.py` (step 5): pairing predicate,
paired-diff math on hand-computed values incl. zero-variance guard,
metric-intersection tolerance, deterministic CSV output, writer smoke,
legacy-tree failure message. Pattern: fabricated tmp_path trees, like
`tests/monitoring/conftest.py` fixtures.

## Done criteria

ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] The end-to-end check in step 4 produces `comparison.csv` + 4 PDFs and
      reports paired diffs of (near-)zero for two identically-seeded runs
- [ ] Running the same CLI twice produces byte-identical `comparison.csv`
      and PDFs (`cmp` the files)
- [ ] Pointing the CLI at a legacy-style directory fails with a
      `FileNotFoundError` that names `kpis.csv` or `manifest.json`
- [ ] No file outside the Scope list was modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Plans 009/010 are not DONE, or `kpis.csv` / `manifest.json` /
  `RunPaths.locate` / `KPI_SCHEMA_VERSION` differ from the shapes specified
  here — the upstream plans changed; this plan needs re-reconciling, not
  guessing.
- Any of the four default metric names is absent from `_SUMMARY_METRICS`
  AND from the kpis.csv of a real smoke run — naming drifted; report the
  actual names.
- You feel the need to edit `analysis/paired_comparison.py` to expose a
  helper — copy the ~10-line t-CI computation into `compare_runs.py` instead
  (duplication of small stats math is preferred over touching a
  publication-critical module here).
- Importing `visualization.kpi_family_figures` for reuse pulls in side
  effects (it should not — module-level code is imports and constants — but
  if it does, replicate the savefig pattern locally and report).

## Maintenance notes

- This module is schema-coupled to `kpis.csv` and `manifest.json` — any
  change to either (plan 010's `analysis/kpi_table.py`, main.py's manifest
  dict) must bump `KPI_SCHEMA_VERSION` and revisit `load_run`.
- The paired-diff math intentionally duplicates `paired_comparison.py`'s
  t-CI rather than sharing it; if a third consumer appears, extract a shared
  `analysis/_stats.py` then (not now).
- Natural extensions (backlog, not here): >2-run paired chains, dominance
  across runs (reuse `analysis/stochastic_dominance.py` machinery),
  Holm-Bonferroni across the compared metric set, and a `--scenario` filter.
