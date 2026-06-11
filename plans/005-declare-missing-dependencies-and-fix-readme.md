# Plan 005: Declare scipy/matplotlib/pytest in requirements.txt and fix the stale README structure block

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- requirements.txt README.md`
> If either file changed since this plan was written, compare the "Current
> state" excerpts against the live files before proceeding; on a mismatch,
> treat it as a STOP condition.

## Status

- **Priority**: P1 (trivial, unblocks any fresh-environment install)
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx / docs
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

A fresh `pip install -r requirements.txt` produces a broken environment: `scipy` is imported on the KPI-aggregation critical path (`analysis/_kpi_shared.py:19`, `analysis/paired_comparison.py:19` — every baseline run hits it via `summary_rows`) and `matplotlib` is imported by two figure producers (`visualization/kpi_family_figures.py:20`, `visualization/policy_comparison_figure.py:25`), yet neither is declared; `pytest` (the verification command for the whole repo) is also undeclared. Separately, the README's Project Structure block points contributors — and agents navigating by path — at a `monitoring/` package that no longer exists and a `utils/helpers.py` that never did, costing wasted lookups.

## Current state

`requirements.txt` (entire file, 4 lines, no trailing newline):

```
simpy>=4.1.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.17.0
```

Undeclared imports (verified):

- `analysis/_kpi_shared.py:19` and `analysis/paired_comparison.py:19` — `from scipy import stats`
- `visualization/kpi_family_figures.py:20` and `visualization/policy_comparison_figure.py:25` — `import matplotlib`
- `tests/` suite — run with pytest (also uses `from scipy import stats` in `tests/monitoring/test_aggregate.py:10`)

`README.md:119-127` (the stale block inside the Project Structure section):

```
monitoring/
  waste_monitor.py          Per-entity tracking of volumes, costs, emissions, events
  baseline_aggregate.py     KPI extraction from monitor history
  scenario_comparison.py    Cross-scenario analysis
  visualization/            Plotly-based charts and temporal comparisons
utils/
  unit_conversion.py        Tonnes to m3 conversion
  capacity_utils.py         Storage overflow decision logic
  helpers.py                Shared utilities
```

Reality on disk: there is no `monitoring/` directory. `waste_monitor.py` lives in `instrumentation/` (beside `mass_balance.py` and `history_store.py`); `baseline_aggregate.py` lives in `analysis/` (beside `paired_comparison.py`, `stochastic_dominance.py`, `pareto.py`, `bullwhip.py`, `flow_times.py`); `scenario_comparison.py` and `temporal_comparison.py` live in `visualization/` (a top-level package, not nested). `utils/` contains exactly `capacity_utils.py`, `seasonality.py`, `unit_conversion.py` — no `helpers.py`. Before editing, confirm with `ls instrumentation analysis visualization utils` and mirror what you see; also skim the rest of the README structure section for any other phantom entries and correct those too.

Convention: each fact lives in ONE doc — keep README entries to one-line role descriptions; deeper guidance belongs to CLAUDE.md/CONTEXT.md (do not duplicate their content).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Verify imports exist | `grep -rn "from scipy import\|import matplotlib" --include='*.py' analysis/ visualization/ \| grep -v __pycache__` | the four files listed above |
| Verify versions in known-good env | `/mnt/c/Python313/python.exe -c "import scipy, matplotlib, pytest; print(scipy.__version__, matplotlib.__version__, pytest.__version__)"` | three version strings |
| Full fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass |

## Scope

**In scope**:

- `requirements.txt`
- `README.md` (the Project Structure section only)

**Out of scope** (do NOT touch):

- No lockfile, no `pyproject.toml`, no CI workflow — those are separate backlog items (see plans/README.md); keep this surgical.
- CLAUDE.md / CONTEXT.md — already accurate.
- Any `.py` file.

## Git workflow

- Two commits, matching the repo's one-concern-per-commit style: `Declare scipy, matplotlib, and pytest dependencies` and `Fix stale package paths in README structure`.
- No `Co-Authored-By`. Do NOT push.

## Steps

### Step 1: Extend requirements.txt

Run the version-check command above, then add floor pins one major-compatible step below the installed versions (matching the existing `>=` style), e.g.:

```
simpy>=4.1.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.17.0
scipy>=1.10.0
matplotlib>=3.7.0
pytest>=7.0.0
```

Adjust the three new floors downward only if the installed versions are older than shown (they should not be on Python 3.13).

**Verify**: `grep -c ">=" requirements.txt` → `7`.

### Step 2: Fix the README structure block

Replace the `monitoring/` pseudo-package with real entries for `instrumentation/`, `analysis/`, and `visualization/`, each listing its actual key files with one-line roles (confirm against `ls` output). Remove the phantom `utils/helpers.py` line and add the real `utils/seasonality.py`. Keep the block's existing indentation/format.

**Verify**: `grep -n "monitoring/\|helpers.py" README.md` → no matches (if "monitoring" legitimately appears elsewhere in prose about the *concept*, leave that; only the structure block paths must go).

### Step 3: Full suite

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass (no code touched; this confirms a clean tree).

## Test plan

None — no executable behavior changes. The grep done-criteria are the regression guards.

## Done criteria

- [ ] `requirements.txt` declares scipy, matplotlib, pytest with `>=` floors
- [ ] `grep -n "helpers.py" README.md` → no matches; structure block names `instrumentation/`, `analysis/`, `visualization/` matching `ls`
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `git status` clean except `requirements.txt`, `README.md`, `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `requirements.txt` or the README block differs from the excerpts (drift).
- The version-check command fails for any of the three packages in `/mnt/c/Python313/python.exe` (the known-good env would be missing a dep — report, don't install).

## Maintenance notes

- Backlog items deliberately NOT done here (recorded in plans/README.md): a lockfile / `pyproject.toml` with `[tool.pytest.ini_options]`, a CI workflow, lint config. If the maintainer adds CI later, the now-complete requirements.txt is what makes `pip install -r requirements.txt && pytest` work on a clean runner.
- Reviewer scrutiny: floors should be permissive (`>=`), not exact pins — this repo intentionally has no lockfile yet.
