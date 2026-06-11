# Plan 009: Add the RunPaths module, Run Name slug, manifest, and LATEST pointer

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 566a59e..HEAD -- config/ tests/config/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (purely additive — no existing caller changes)
- **Depends on**: none
- **Category**: tech-debt (output reorganization, phase 1 of 3)
- **Planned at**: commit `566a59e`, 2026-06-11

## Why this matters

Today a re-run of `python main.py --mode baseline --scenario Baseline` silently
overwrites `outputs/baseline/Baseline/`, and no artifact records when a run
happened, which code version produced it, or what the scenario parameters were.
The project's own domain glossary (`CONTEXT.md`, entries **Run** and
**Run Name**) already specifies the fix — every run gets its own directory named
by an auto-generated slug, holding a config snapshot — but the code never
implemented it. This plan adds the machinery (a `config/paths.py` module) as
pure new code with tests. Plan 010 wires `main.py` onto it; plan 011 builds
cross-run comparison on top. Nothing in this plan changes any existing
behavior.

## Current state

- `config/constants.py:115-124` — the only path constants today (keep them;
  plan 010 uses some as fallbacks):

  ```python
  # Output artifact roots (clean-monitoring issue 12). Single source of truth for
  # where the simulation writes run data and plots, ...
  OUTPUT_ROOT = "outputs"
  PLOTS_ROOT = "plots"
  BASELINE_OUTPUT_ROOT = f"{OUTPUT_ROOT}/baseline"
  BASELINE_SCENARIO_DEFAULT = f"{BASELINE_OUTPUT_ROOT}/Baseline"
  SCENARIO_COMPARISON_PLOTS_DIR = f"{PLOTS_ROOT}/scenario_comparison"
  ```

- `config/paths.py` — does not exist yet. You create it.
- `tests/config/` — existing test package for config modules; your tests go
  there.
- `CONTEXT.md:302-320` — the authoritative spec for the slug. Quoted here so
  you do not need to interpret it:

  > **Run**: One invocation of `main.py` — the entire batch of simulations it
  > produces. ... Runs are identified by a generated name encoding mode,
  > variant, and flags, and all artifacts (config snapshot, results, plots,
  > per-replication data) live in a single run directory.
  >
  > **Run Name**: An auto-generated slug that identifies a run at a glance:
  > `{mode}_{variant}_{flags}__{HHMM}`. Mode is the execution shape (`grid`,
  > `baseline`). Variant is the scenario filter, present only when `--scenario`
  > restricts to one (omitted when running all scenarios). Flags are
  > non-default parameters (`n50` for 50 replications). The `__HHMM` suffix
  > disambiguates same-config runs on the same day.

- Repo conventions that apply (from `CLAUDE.md`):
  - Variable names verbose and descriptive, never abbreviated.
  - No emojis in code or comments.
  - All constants live in `config/constants.py` — the new module may define
    path-building *logic*, but any new literal root goes in `constants.py`.
  - Surgical changes only; do not refactor adjacent code.
- Determinism convention (`CLAUDE.md`, `tests/test_determinism.py`): run
  artifacts must be byte-identical for a given seed across invocations. The
  slug and manifest are deliberately the ONLY timestamped artifacts, which is
  why `generate_run_name` must take the time as a parameter instead of calling
  `datetime.now()` internally — callers inject it, tests pin it.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Full test suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass (baseline before you start: 261 passed + skips) |
| Just your new tests | `/mnt/c/Python313/python.exe -m pytest tests/config/test_run_paths.py -q` | all pass |
| Import smoke check | `/mnt/c/Python313/python.exe -c "from config.paths import RunPaths, generate_run_name"` | exit 0, no output |

The WSL system `python3` has no dependencies installed — always use
`/mnt/c/Python313/python.exe`.

## Scope

**In scope** (the only files you should create or modify):
- `config/paths.py` (create)
- `config/constants.py` (add ONE constant: `RUNS_ROOT`)
- `tests/config/test_run_paths.py` (create)

**Out of scope** (do NOT touch, even though they look related):
- `main.py` — wiring happens in plan 010.
- `analysis/*`, `visualization/*` — their CLI defaults change in plan 010.
- The existing constants `OUTPUT_ROOT`, `PLOTS_ROOT`, `BASELINE_OUTPUT_ROOT`,
  `BASELINE_SCENARIO_DEFAULT`, `SCENARIO_COMPARISON_PLOTS_DIR` — do not delete
  or rename them.
- `outputs/` and `plots/` on disk — never write into or delete real run data.
- `CONTEXT.md` — the slug spec is implemented as written, not amended.

## Git workflow

- Branch: `advisor/009-run-paths-module`
- Commit style (repo convention): imperative mood, under 72 chars, no colon
  after the verb — e.g. `Add RunPaths module and run name slug generator`.
  Body explains why. Do NOT add Co-Authored-By lines. Do NOT push.

## Steps

### Step 1: Add the `RUNS_ROOT` constant

In `config/constants.py`, directly after the existing
`SCENARIO_COMPARISON_PLOTS_DIR` line (~line 124), add:

```python
# Per-run artifact tree (ADR 0020). Every main.py invocation gets its own
# directory under RUNS_ROOT, named by the Run Name slug (CONTEXT.md), holding
# manifest, per-replication data, summaries, and figures.
RUNS_ROOT = f"{OUTPUT_ROOT}/runs"
```

**Verify**: `/mnt/c/Python313/python.exe -c "from config.constants import RUNS_ROOT; print(RUNS_ROOT)"` → prints `outputs/runs`

### Step 2: Create `config/paths.py`

Create the module with this exact public surface (docstrings shortened here;
write real ones). It must import only from the standard library and
`config.constants` — importing from `analysis`/`core`/`visualization` would
create an import cycle (see `tests/test_import_isolation.py`).

```python
"""Run-directory path authority (ADR 0020).

Implements the Run / Run Name convention from CONTEXT.md: one directory per
main.py invocation under RUNS_ROOT, named {mode}_{variant}_{flags}__{HHMM}.
RunPaths is the ONLY component that creates output directories; writers ask it
for destinations instead of calling makedirs themselves.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config.constants import RUNS_ROOT

LATEST_POINTER_FILENAME = "LATEST"
MANIFEST_FILENAME = "manifest.json"
KPI_TABLE_FILENAME = "kpis.csv"


def generate_run_name(
    mode: str,
    scenario_filter: str | None,
    replications: int | None,
    default_replications: int,
    hour: int,
    minute: int,
) -> str:
    """Build the Run Name slug {mode}_{variant}_{flags}__{HHMM}.

    Variant appears only when scenario_filter is set. Flags currently encode
    only a non-default replication count as nNN (CONTEXT.md). Time components
    are injected by the caller so artifacts stay reproducible in tests.
    """


@dataclass(frozen=True)
class RunPaths:
    """Path authority for one run directory. Construct via RunPaths.create()."""

    runs_root: Path
    run_name: str

    # --- construction -----------------------------------------------------
    @classmethod
    def create(cls, run_name: str, runs_root: Path | None = None) -> "RunPaths":
        """Create the run directory (collision-suffixed -2, -3, ... if the
        slug already exists) and return the RunPaths for it."""

    @classmethod
    def locate(cls, run_reference: str | None, runs_root: Path | None = None) -> "RunPaths":
        """Resolve an existing run: explicit path -> use it; bare slug ->
        runs_root/slug; None -> read the LATEST pointer. Raises
        FileNotFoundError with a actionable message if nothing resolves."""

    # --- destinations (each mkdir(parents=True, exist_ok=True) on access) --
    @property
    def run_dir(self) -> Path: ...
    def scenario_dir(self, scenario_name: str) -> Path: ...
    def combo_dir(self, scenario_name: str, inventory_policy_value: str, stock_strategy_value: str) -> Path:
        """{run_dir}/{scenario}/{policy}__{strategy}/ — same combo naming as
        the legacy tree, so analysis globs (*/summary.csv) keep working."""
    def scenario_figures_dir(self, scenario_name: str) -> Path:
        """{run_dir}/{scenario}/figures/"""
    @property
    def manifest_path(self) -> Path: ...
    @property
    def kpi_table_path(self) -> Path: ...

    # --- side effects -------------------------------------------------------
    def write_manifest(self, manifest: dict) -> Path:
        """json.dump with indent=2 and sort_keys=True to manifest_path."""
    def mark_latest(self) -> Path:
        """Write this run_name (plus newline) into {runs_root}/LATEST."""
```

Implementation requirements, in order of importance:

1. `generate_run_name` examples (encode these as tests in step 3):
   - `("baseline", "Baseline", 100, 100, 14, 32)` → `baseline_Baseline__1432`
     (replications equal to default → no flag)
   - `("baseline", None, 50, 100, 9, 5)` → `baseline_n50__0905`
     (no variant; flag `n50`; HHMM zero-padded)
   - `("grid", None, None, 100, 23, 59)` → `grid__2359`
     (grid has no replications; `None` means "no flag")
   - Segments are joined with single underscores; the time is always preceded
     by a double underscore, exactly as in CONTEXT.md.
2. `create()` collision handling: if `{runs_root}/{run_name}` exists, try
   `{run_name}-2`, `{run_name}-3`, ... and return a `RunPaths` whose
   `run_name` is the suffixed one. Never overwrite or reuse an existing
   directory.
3. `locate()` resolution order: if `run_reference` is a path that exists on
   disk (as given or relative to cwd), use its parent/name; elif
   `{runs_root}/{run_reference}` exists, use that; elif `run_reference is None`,
   read `{runs_root}/LATEST` (strip whitespace) and resolve that slug. A
   missing LATEST or unresolvable slug raises `FileNotFoundError` naming what
   was tried.
4. `runs_root` defaults to `Path(RUNS_ROOT)` in both classmethods. Keep it a
   parameter so tests use `tmp_path` and plan 010 can honor `--out-root`.
5. The frozen dataclass plus directory creation on *access* (inside the
   property/method bodies) — not in `__post_init__` — so constructing a
   `RunPaths` via `locate()` never creates directories for scenarios that do
   not exist in that run.

**Verify**: `/mnt/c/Python313/python.exe -c "from config.paths import RunPaths, generate_run_name; print(generate_run_name('baseline', 'Baseline', 100, 100, 14, 32))"` → prints `baseline_Baseline__1432`

### Step 3: Write the tests

Create `tests/config/test_run_paths.py`. Model the style on the existing
`tests/monitoring/test_aggregate.py` (plain pytest functions, `tmp_path`
fixtures, no classes needed). Cover, at minimum:

1. The three slug examples from step 2 (exact string equality).
2. Zero-padding: hour 9, minute 5 → suffix `__0905`.
3. `create()` makes the directory under a `tmp_path` runs root.
4. `create()` collision: pre-create `tmp_path/"baseline_Baseline__1432"`, call
   `create()` with the same slug, assert the returned `run_name` is
   `baseline_Baseline__1432-2` and the `-2` directory exists; repeat once more
   for `-3`.
5. `combo_dir("Baseline", "push", "on_demand")` returns
   `{run_dir}/Baseline/push__on_demand` and the directory exists afterward.
6. `write_manifest({"b": 1, "a": 2})` produces a file whose text starts with
   `{\n  "a": 2` (sort_keys honored) and round-trips via `json.loads`.
7. `mark_latest()` then `RunPaths.locate(None, runs_root=tmp_path)` resolves
   back to the same `run_dir`.
8. `locate("no-such-run", runs_root=tmp_path)` raises `FileNotFoundError`.
9. `locate()` with an explicit existing path (the run dir created in 3)
   resolves to it without consulting LATEST.

This suite is the red/blue check (repo convention: every test must fail when
the behavior it pins is broken — spot-check at least one by temporarily
mutating the slug separator, seeing red, and restoring).

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/config/test_run_paths.py -q` → all pass (expect ~9-12 tests)

### Step 4: Full-suite regression

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → same pass
count as the pre-change baseline plus your new tests; zero failures.

## Test plan

Covered by step 3 (the module is new code, so its tests ARE the plan's tests).
No existing test should change.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `/mnt/c/Python313/python.exe -c "from config.paths import RunPaths, generate_run_name"` exits 0
- [ ] `grep -n "RUNS_ROOT" config/constants.py` shows exactly one definition
- [ ] `grep -rn "datetime.now\|time.time\|date.today" config/paths.py` returns no matches (time is injected, never sampled)
- [ ] `git status --short` shows only the three in-scope files changed/added
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `config/paths.py` already exists (someone implemented this since planning).
- The `config/constants.py` excerpt above does not match the live file
  (constants block moved or renamed).
- Importing `config.paths` triggers an import cycle error from
  `tests/test_import_isolation.py` — the config↔data_classes cycle was fixed
  once before and must not be reintroduced; report rather than adding a lazy
  import workaround.
- You find yourself wanting to edit `main.py` "while you're here" — that is
  plan 010.

## Maintenance notes

- Plan 010 consumes every symbol defined here; if you rename anything, 010's
  excerpts drift. Prefer implementing exactly the surface above.
- The slug spec lives in `CONTEXT.md` (**Run Name**); if flags beyond `nNN`
  are ever encoded (e.g. worker count), the glossary entry must be updated in
  the same change.
- `LATEST` is a plain text file rather than a symlink deliberately: the repo
  lives on `/mnt/c` (Windows NTFS via WSL DrvFs) where symlink support is
  unreliable.
- Record the overall output-reorganization decision as ADR 0020 when plan 010
  lands (deferred there so the ADR describes shipped behavior).
