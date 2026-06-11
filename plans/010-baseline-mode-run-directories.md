# Plan 010: Write baseline runs into per-run directories with manifest and KPI table

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 566a59e..HEAD -- main.py analysis/ visualization/ config/ tests/test_determinism.py tests/monitoring/`
> Plan 009 MUST be DONE first (this plan imports `config.paths`). main.py
> had an uncommitted change at planning time (the KPI-family figure loop) —
> the excerpts below include it; if `git status` shows main.py still dirty,
> ask the maintainer to commit it before you branch.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (touches the production artifact path; mitigated by the
  determinism suite and the frozen legacy tree)
- **Depends on**: plans/009-run-paths-module-and-manifest.md
- **Category**: tech-debt (output reorganization, phase 2 of 3)
- **Planned at**: commit `566a59e`, 2026-06-11

## Why this matters

Baseline Monte Carlo runs currently write into a fixed tree
(`outputs/baseline/{scenario}/{combo}/`), so a re-run silently overwrites the
previous dataset, and no artifact records when the run happened, which code
produced it, or what the scenario parameters were. After this plan, every
`--mode baseline` invocation lands in its own slug-named directory under
`outputs/runs/` with a `manifest.json` (provenance), a tidy `kpis.csv` (the
substrate plan 011's cross-run comparison reads), gzipped raw sidecars
(~10:1 smaller), and figures grouped under `figures/`. The old
`outputs/baseline/` tree is frozen in place as legacy — never written again,
never deleted.

## Current state

### Target layout (what this plan produces)

```
outputs/runs/
├── LATEST                                   ← text file: last run's slug
└── baseline_Baseline_n50__1432/             ← Run Name slug (plan 009)
    ├── manifest.json
    ├── kpis.csv                             ← tidy long-format KPI table
    └── Baseline/
        ├── push__on_demand/
        │   ├── run_000.json …               (unchanged schema)
        │   ├── raw_000.json.gz …            (gzipped, mtime=0)
        │   └── summary.csv                  (unchanged schema)
        ├── … five more combos …
        ├── paired_comparison.csv            (unchanged, scenario root)
        ├── stochastic_dominance.csv
        ├── pareto_frontier.csv
        └── figures/
            ├── policy_comparison.pdf  pareto_frontier.pdf
            ├── bullwhip_comparison.pdf  residence_comparison.pdf
            ├── carbon_comparison.pdf  service_by_product_comparison.pdf
```

### Key facts about the code as it exists today

- `main.py:153-186` — `run_monte_carlo_baseline(replications, scenario_filter, out_root, workers)`;
  `out_root` defaults to `Path(BASELINE_OUTPUT_ROOT)` (= `outputs/baseline`):

  ```python
  base_seed = DEFAULT_BASE_SEED  # deterministic seed series across runs
  out_root = Path(BASELINE_OUTPUT_ROOT) if out_root is None else Path(out_root)
  out_root.mkdir(parents=True, exist_ok=True)
  ```

- `main.py:193-200` — scenario and combo dirs are created inline:

  ```python
  scenario_dir = out_root / scenario_name
  scenario_dir.mkdir(parents=True, exist_ok=True)
  ...
  combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
  combo_dir.mkdir(parents=True, exist_ok=True)
  ```

- `main.py:131-140` — the raw sidecar write inside the worker task
  `_run_baseline_replication_task` (runs in subprocesses when `--workers > 1`;
  the function is module-level so it pickles under spawn):

  ```python
  raw_path = combo_dir / f"raw_{replication_index:03d}.json"
  try:
      with open(raw_path, "w", encoding="utf-8") as f:
          json.dump(
              jsonify(build_raw_payload(simulation_result["monitor_data"])),
              f,
              separators=(",", ":"),
          )
  ```

- `main.py:254-307` — after the replication loop, per scenario, the callers
  pass `scenario_dir` to: `write_paired_comparison_report`,
  `write_dominance_report`, `write_pareto_report` + `write_pareto_plot`,
  `write_policy_comparison_figure`, and a loop over the four KPI-family figure
  producers. Every figure producer has the signature
  `write_*_figure(path, filename: str = "<name>.pdf")` and saves to
  `path / filename` — so writing into a `figures/` subdirectory needs **no
  signature change**: pass `filename="figures/<name>.pdf"` once the directory
  exists. They all read `{path}/*/summary.csv` via
  `analysis.pareto.iter_combo_summaries(path, root=False)`.
- The figure PDFs already pin `CreationDate`/`ModDate` to epoch for
  byte-stability (`visualization/policy_comparison_figure.py:204-208`).
- `extract_kpis` (`analysis/baseline_aggregate.py:135`) returns a dict whose
  values are floats EXCEPT the namespace keys, which are one-level nested
  dicts: `bullwhip`, `residence`, `carbon`, `availability`,
  `service_level_full_by_product_pct` (see `_GENERIC_NAMESPACES` in
  `analysis/_kpi_shared.py`).
- The six standalone CLIs default their path argument to
  `BASELINE_SCENARIO_DEFAULT` (= `outputs/baseline/Baseline`), each inside its
  `if __name__ == "__main__":` block: `analysis/paired_comparison.py:203-212`,
  `analysis/pareto.py:222-231`, `analysis/stochastic_dominance.py:280-290`,
  `visualization/kpi_family_figures.py:392-400`,
  `visualization/policy_comparison_figure.py:215-223`,
  `visualization/pareto_visualization.py:265-273`.
- `tests/test_determinism.py` — three `@pytest.mark.slow` tests (opt-in via
  `--run-slow`) that invoke `main.py --mode baseline ... --out-root {tmp}` as
  subprocesses and compare artifacts byte-for-byte. Two will break under this
  plan and must be updated (step 8): the relative-path comparison assumes
  artifacts sit directly under `out_root` (the slug directory now intervenes,
  and two invocations get different slugs), and the glob pattern
  `raw_*.json` must become `raw_*.json.gz`.
- Repo conventions: verbose variable names, no emojis, constants in
  `config/constants.py`, surgical changes only, commits imperative <72 chars
  no colon, never push.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass |
| Slow determinism suite | `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow` | 3 pass (several minutes) |
| Smoke run | `/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --out-root /tmp/reorg_smoke` | exit 0 |

## Scope

**In scope** (the only files you should modify/create):
- `main.py`
- `config/paths.py` (add `resolve_default_scenario_dir`)
- `analysis/baseline_aggregate.py` (add `KPI_SCHEMA_VERSION` only)
- `analysis/kpi_table.py` (create)
- The six `__main__` blocks listed above (default-path resolution only)
- `tests/test_determinism.py`, `tests/monitoring/test_kpi_table.py` (create)
- `CLAUDE.md` (update the run/output documentation), `docs/adr/0020-*.md` (create)

**Out of scope** (do NOT touch):
- Grid mode (`main()` function), `visualization/mfa_visualization.py`,
  `visualization/scenario_comparison.py`, `instrumentation/waste_monitor.py`
  (its `PLOTS_ROOT` makedirs side effect stays for now — grid mode still
  depends on `plots/` existing; relocating grid output is deferred backlog).
- The legacy `outputs/baseline/` tree on disk — frozen, never written, never
  deleted.
- `run_NNN.json` content schema, `summary.csv` header, the `run_{i:03d}`
  filename convention (CRN pairing in `analysis/paired_comparison.py` depends
  on it), and `extract_kpis` keys.
- The constants `BASELINE_OUTPUT_ROOT` / `BASELINE_SCENARIO_DEFAULT` — still
  referenced as the legacy fallback; do not delete.
- `.scratch/paper-draft-audit/` scripts — they read the frozen legacy tree.

## Git workflow

- Branch: `advisor/010-baseline-run-directories`
- One commit per step or logical unit; imperative, <72 chars, no colon, no
  Co-Authored-By. Do NOT push.

## Steps

### Step 1: Add the KPI schema version

In `analysis/baseline_aggregate.py`, directly above `_SUMMARY_METRICS`
(~line 20), add:

```python
# Bump whenever extract_kpis() keys change shape or meaning, so cross-run
# tooling (manifest.json, analysis/compare_runs.py) can refuse or flag
# mismatched datasets instead of comparing different quantities silently.
KPI_SCHEMA_VERSION = 1
```

**Verify**: `/mnt/c/Python313/python.exe -c "from analysis.baseline_aggregate import KPI_SCHEMA_VERSION; print(KPI_SCHEMA_VERSION)"` → `1`

### Step 2: Create the tidy KPI table writer

Create `analysis/kpi_table.py` with two functions (pure logic + thin writer,
matching the `summary_rows` / `_write_combo_summary` split the repo already
uses — see `analysis/baseline_aggregate.py:71` and `main.py:315-318`):

```python
KPI_TABLE_HEADER = "scenario,inventory_policy,stock_strategy,replication,seed,metric,value"

def flatten_kpis(kpis: dict) -> dict[str, float]:
    """Flatten one-level namespace dicts (bullwhip, residence, carbon,
    availability, service_level_full_by_product_pct) into dot-joined keys,
    e.g. {"bullwhip": {"treatment_anchored": 2.0}} -> {"bullwhip.treatment_anchored": 2.0}.
    Sort keys alphabetically for a stable row order."""

def kpi_table_rows(replication_records: list[dict]) -> list[str]:
    """Header plus one CSV row per (record, metric). Records are the dicts
    run_monte_carlo_baseline accumulates: base_scenario, inventory_policy,
    stock_strategy, seed, replication_index, kpis. Use repr-free formatting:
    str(value) for floats, empty string for None."""
```

Row order must be deterministic: records in input order (the caller sorts),
metrics alphabetical within a record.

**Verify**: `/mnt/c/Python313/python.exe -c "from analysis.kpi_table import kpi_table_rows; print(kpi_table_rows([{'base_scenario':'S','inventory_policy':'push','stock_strategy':'on_demand','seed':42,'replication_index':0,'kpis':{'a':1.0,'b':{'c':2.0}}}]))"` → header row then `S,push,on_demand,0,42,a,1.0` then `S,push,on_demand,0,42,b.c,2.0`

### Step 3: Switch `run_monte_carlo_baseline` onto RunPaths

In `main.py`:

1. Add imports: `from config.paths import RunPaths, generate_run_name` and
   `from analysis.baseline_aggregate import extract_kpis, summary_rows, KPI_SCHEMA_VERSION`
   (extend the existing line 7 import), `from analysis.kpi_table import kpi_table_rows`,
   plus `import dataclasses`, `import gzip`, `import subprocess`,
   `from datetime import datetime, timezone`.
2. Change the signature to
   `run_monte_carlo_baseline(replications=100, scenario_filter=None, out_root=None, workers=1, write_raw=True)`.
3. Replace the `out_root` block (`main.py:185-186` excerpt above) with:

   ```python
   invocation_time = datetime.now(timezone.utc)
   run_name = generate_run_name(
       mode="baseline",
       scenario_filter=scenario_filter,
       replications=replications,
       default_replications=100,
       hour=invocation_time.hour,
       minute=invocation_time.minute,
   )
   runs_root = Path(out_root) if out_root is not None else None
   run_paths = RunPaths.create(run_name, runs_root=runs_root)
   print(f"Run directory: {run_paths.run_dir}")
   ```

   (`--out-root` keeps existing CLI spelling but now means "parent directory
   for run directories" — update its `help=` text accordingly, and drop the
   now-unused `BASELINE_OUTPUT_ROOT` import from `main.py` line 2 only if
   nothing else in the file uses it.)
4. Replace `scenario_dir = out_root / scenario_name; scenario_dir.mkdir(...)`
   with `scenario_dir = run_paths.scenario_dir(scenario_name)`, and
   `combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"; combo_dir.mkdir(...)`
   with `combo_dir = run_paths.combo_dir(scenario_name, policy.value, strategy.value)`
   (both occurrences — task building ~line 199 and the summary loop ~line 232).
5. Thread `write_raw` into the replication task tuple and
   `_run_baseline_replication_task` signature (add a trailing
   `write_raw: bool` parameter — keep it positional in the tuple so the pool
   `submit(*task)` call needs no other change).

**Verify**: `/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 1 --out-root /tmp/reorg_step3` → exit 0; `ls /tmp/reorg_step3` shows `LATEST`-less (LATEST comes in step 6) single directory named `baseline_Baseline_n1__HHMM` containing `Baseline/push__on_demand/run_000.json` etc.

### Step 4: Gzip the raw sidecar and honor `write_raw`

In `_run_baseline_replication_task`, replace the raw write block
(`main.py:131-140` excerpt above) with:

```python
if write_raw:
    raw_path = combo_dir / f"raw_{replication_index:03d}.json.gz"
    try:
        raw_bytes = json.dumps(
            jsonify(build_raw_payload(simulation_result["monitor_data"])),
            separators=(",", ":"),
        ).encode("utf-8")
        with open(raw_path, "wb") as raw_file:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_file, mtime=0
            ) as gz:
                gz.write(raw_bytes)
    except Exception as e:
        print(f"Warning: failed to write {raw_path}: {e}")
```

`filename=""` and `mtime=0` are load-bearing: gzip embeds both in the header
by default, which would break the byte-identity the determinism suite pins.

Add the CLI flag in the `__main__` block:

```python
parser.add_argument(
    "--no-raw",
    action="store_true",
    help="Skip raw_NNN.json.gz sidecars (smaller runs; new KPIs then need a re-run)",
)
```

and pass `write_raw=not args.no_raw` through.

**Verify**:
`/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 1 --out-root /tmp/reorg_step4 && /mnt/c/Python313/python.exe -c "import gzip,glob,json; p=glob.glob('/tmp/reorg_step4/*/Baseline/push__on_demand/raw_000.json.gz')[0]; json.loads(gzip.open(p).read()); print('ok')"` → `ok`

### Step 5: Route figures into `figures/`

In the per-scenario tail of `run_monte_carlo_baseline` (`main.py:254-307`),
before the figure calls add
`run_paths.scenario_figures_dir(scenario_name)` (creates the directory), then
change ONLY the figure producers — the three CSV reports keep writing to the
scenario root:

- `write_pareto_plot(scenario_dir)` → `write_pareto_plot(scenario_dir, filename="figures/pareto_frontier.pdf")`
- `write_policy_comparison_figure(scenario_dir)` → `write_policy_comparison_figure(scenario_dir, filename="figures/policy_comparison.pdf")`
- In the KPI-family loop, replace the bare producer tuple with
  producer/filename pairs and call
  `kpi_figure_producer(scenario_dir, filename=f"figures/{figure_filename}")`
  using each producer's current default name
  (`bullwhip_comparison.pdf`, `residence_comparison.pdf`,
  `carbon_comparison.pdf`, `service_by_product_comparison.pdf`).

**Verify**: rerun the step-3 smoke command into `/tmp/reorg_step5`; `ls /tmp/reorg_step5/*/Baseline/figures/` → six PDFs; `ls /tmp/reorg_step5/*/Baseline/*.csv` → `paired_comparison.csv pareto_frontier.csv stochastic_dominance.csv` (dominance needs n>=2 replications to be meaningful but the file should exist; if a report returns None for n=1 that is fine — use `--replications 2` for this check).

### Step 6: Write `kpis.csv`, `manifest.json`, and `LATEST`

At the end of `run_monte_carlo_baseline`, after the scenario loop and before
the elapsed-time print:

```python
results.sort(key=lambda record: (
    record["base_scenario"], record["inventory_policy"],
    record["stock_strategy"], record["replication_index"],
))
run_paths.kpi_table_path.write_text(
    "\n".join(kpi_table_rows(results)), encoding="utf-8"
)

manifest = {
    "run_name": run_paths.run_name,
    "created_at": invocation_time.isoformat(),
    "mode": "baseline",
    "replications": replications,
    "base_seed": base_seed,
    "workers": workers,
    "write_raw": write_raw,
    "scenario_filter": scenario_filter,
    "scenarios": {
        scenario_name: dataclasses.asdict(get_scenario_config(scenario_name))
        for scenario_name in scenarios
    },
    "kpi_schema_version": KPI_SCHEMA_VERSION,
    "git_sha": _read_git_sha(),
    "git_dirty": _read_git_dirty(),
}
run_paths.write_manifest(manifest)
run_paths.mark_latest()
```

Add the two module-level helpers near `_write_combo_summary`: each runs
`subprocess.run(["git", "rev-parse", "--short", "HEAD"], ...)` /
`["git", "status", "--porcelain"]` with `capture_output=True, text=True,
timeout=10` and returns `None` on ANY failure (git absent, not a repo) —
provenance is best-effort, a missing git must never fail a run.
`ScenarioConfig` is a `@dataclass` (`config/base_config.py:40-41`), so
`dataclasses.asdict` works; if it raises, see STOP conditions.

**Verify**: rerun the smoke into `/tmp/reorg_step6`; `cat /tmp/reorg_step6/LATEST` → the slug; `/mnt/c/Python313/python.exe -c "import json,glob; m=json.load(open(glob.glob('/tmp/reorg_step6/*/manifest.json')[0])); print(m['kpi_schema_version'], m['base_seed'], sorted(m['scenarios']))"` → `1 42 ['Baseline']` (base seed is `DEFAULT_BASE_SEED` — print it first if unsure); `head -2 /tmp/reorg_step6/*/kpis.csv` → the header then a data row.

### Step 7: Point the six standalone CLIs at the latest run

In `config/paths.py`, add:

```python
def resolve_default_scenario_dir(scenario_name: str = "Baseline") -> str:
    """Default path for the standalone analysis/figure CLIs: the named
    scenario inside the latest run (via the LATEST pointer), falling back to
    the frozen legacy tree (BASELINE_SCENARIO_DEFAULT) when no run exists."""
```

Implementation: try `RunPaths.locate(None)`; if it resolves and
`{run_dir}/{scenario_name}` exists, return that as a string; on
`FileNotFoundError` (or missing scenario subdir) return
`BASELINE_SCENARIO_DEFAULT` (import it inside the function from
`config.constants`).

Then in each of the six `__main__` blocks (exact locations in Current state),
replace `default=BASELINE_SCENARIO_DEFAULT` with
`default=resolve_default_scenario_dir()` and swap the import
`from config.constants import BASELINE_SCENARIO_DEFAULT` for
`from config.paths import resolve_default_scenario_dir`. Update each `help=`
string to say "default: latest run's Baseline scenario, else the legacy
outputs/baseline/Baseline". Touch nothing else in those files.

**Verify**: `cd /mnt/c/Users/kovac/Desktop/"Current work"/wood_waste_management_DES && /mnt/c/Python313/python.exe -m analysis.paired_comparison --help` → help text mentions the latest-run default; `/mnt/c/Python313/python.exe -m pytest tests/test_analysis_entry_points.py -q` → pass.

### Step 8: Update the determinism tests

In `tests/test_determinism.py`:

1. Add a helper `_single_run_dir(out_root: Path) -> Path` returning the one
   subdirectory of `out_root` that is a directory (assert exactly one,
   ignoring the `LATEST` file).
2. In `test_baseline_runs_are_byte_identical_across_processes` and
   `test_parallel_baseline_matches_sequential_byte_for_byte`, compute
   relative paths against `_single_run_dir(out_x)` instead of `out_x`, so the
   differing slug directories (different HHMM, or `-2` suffix) cancel out.
   **Exclude `manifest.json` from byte comparison** — it carries the
   timestamp by design; everything else must still match byte-for-byte.
   `kpis.csv` and `LATEST` content (modulo slug) are also expected to be
   byte-identical apart from nothing — include `kpis.csv` in the compared
   patterns; exclude `LATEST`.
3. Change the pattern tuple `("run_*.json", "raw_*.json", "summary.csv")` to
   `("run_*.json", "raw_*.json.gz", "summary.csv", "kpis.csv")`.
4. `test_generation_floor_is_policy_invariant` needs no logic change
   (`rglob` still finds the run JSONs through the slug directory).

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow` → 3 passed (this is the plan's critical gate: gzip mtime/filename handling and worker-pool path threading are proven here).

### Step 9: Tests for the new table module

Create `tests/monitoring/test_kpi_table.py` (style: plain pytest functions
like `tests/monitoring/test_aggregate.py`): header exactness, dot-flattening
of one nested namespace, alphabetical metric order, multi-record row order
following input order, None rendered as empty string. Mutate one assertion to
red and restore (repo red/blue convention) — note doing so in your report.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/monitoring/test_kpi_table.py -q` → all pass.

### Step 10: Documentation

1. `CLAUDE.md` — in "Running Simulations", change the outputs line to
   `Outputs: outputs/runs/{run_name}/{scenario}/{policy}__{strategy}/` and the
   paired-comparison example to note CLIs default to the latest run. Mention
   `--no-raw`. Keep edits minimal.
2. Create `docs/adr/0020-per-run-output-directories.md` (follow the header
   format of `docs/adr/0019-inventory-position-is-on-hand-only.md`): decision
   = per-run directories under `outputs/runs/` implementing CONTEXT.md's
   Run/Run Name; manifest carries the only timestamp; raw sidecars gzipped
   with `mtime=0`; legacy `outputs/baseline/` frozen in place; grid mode
   deferred. ADRs are append-only — do not edit earlier ADRs.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass.

## Test plan

- New: `tests/monitoring/test_kpi_table.py` (step 9).
- Updated: `tests/test_determinism.py` (step 8) — still the strongest gate;
  run with `--run-slow`.
- Full suite green throughout; the only behavioral deltas tests should see
  are the run-dir layer, the `.gz` suffix, and the new files.

## Done criteria

ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow` → 3 passed
- [ ] Smoke run produces, under one slug directory: `manifest.json`,
      `kpis.csv`, and per combo `run_*.json` + `raw_*.json.gz` + `summary.csv`,
      with six PDFs in `{scenario}/figures/` and three CSV reports at the
      scenario root
- [ ] `cat {out_root}/LATEST` equals the slug directory's name
- [ ] Re-running the identical command creates a SECOND directory (suffix
      `-2` or different HHMM) — `outputs` of the first run untouched
- [ ] `grep -rn "BASELINE_OUTPUT_ROOT" main.py` returns no matches
- [ ] `git log --oneline outputs/ plots/` shows no commits from you and
      `git status` shows no changes under `outputs/` or `plots/`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Plan 009 is not DONE / `config.paths` does not import.
- `main.py` excerpts do not match the live file beyond the documented
  uncommitted KPI-figure loop.
- `dataclasses.asdict(get_scenario_config(...))` raises — ScenarioConfig may
  hold non-dataclass members; report the actual type rather than improvising
  a serializer.
- The determinism suite fails on raw `.gz` bytes after you have confirmed
  `mtime=0` and `filename=""` — that points at a real nondeterminism, not a
  packaging issue.
- Any figure producer turns out NOT to accept `filename=` with a subdirectory
  component (e.g. it re-derives the directory) — report instead of patching
  the producer.
- You need to modify `iter_combo_summaries` — its glob contract
  (`*/summary.csv`) is shared by six consumers and must not change here.

## Maintenance notes

- The reviewer should scrutinize step 4 (gzip determinism) and step 8 (what
  the determinism tests now exclude — only `manifest.json` and `LATEST`).
- Anything that adds a KPI key must bump `KPI_SCHEMA_VERSION` — say so in the
  PR description so it enters review lore; plan 011's tooling depends on it.
- Deferred follow-ups (do NOT do here): grid-mode relocation onto RunPaths
  (incl. removing `WasteMonitor.__init__`'s `PLOTS_ROOT` makedirs and giving
  `ScenarioComparison` an `output_dir` parameter); new figures for unplotted
  KPI families (cost components, availability, volumes/rates, lost-sales
  split); retiring `.scratch/paper-draft-audit/` once the paper's figures are
  regenerated from a new-style run; deleting the legacy tree.
- After this lands, the first real run should be the full
  `--mode baseline --replications 100` refresh that plans/README.md already
  calls for (the legacy data predates the 001/004 fixes).
