# Plan 001: Make total_emissions_kgco2e sum the per-tick emissions series instead of reading its last element

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- analysis/baseline_aggregate.py instrumentation/waste_monitor.py tests/monitoring/test_aggregate.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (code change is one expression) — but the KPI value changes by orders of magnitude; see Maintenance notes.
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

`total_emissions_kgco2e` is a headline KPI of this research codebase: it is one of the four Pareto objectives (`analysis/pareto.py`), a column in `summary.csv`, an input to the paired-comparison and stochastic-dominance reports, and the y-axis of the paper's Fig. 2 (`visualization/policy_comparison_figure.py`). The extraction in `analysis/baseline_aggregate.py` reads `series[-1]` of each entity's `total_impact` history — but that series is **per-timestamp**, not cumulative: the monitor appends a fresh `0.0` slot for every new timestamp and accumulates only within that slot. So the KPI currently reports only the emissions that occurred in the **final monitoring tick** of the 365-day run, undercounting the true run total by roughly the number of distinct emission timestamps. Every cross-policy emissions comparison built on this number is wrong in magnitude (relative orderings may or may not survive — that is exactly what the fix will reveal).

## Current state

Relevant files:

- `analysis/baseline_aggregate.py` — KPI extraction (`extract_kpis`); contains the bug at lines 171–176.
- `instrumentation/waste_monitor.py` — the writer, `track_environmental_impact` (lines 167–188); appends a new `0.0` per new timestamp, accumulates within the slot. **Do not change this file** — `visualization/temporal_comparison.py:146` already (correctly) does `sum(total_impacts)` over the same series, so changing the writer to cumulative would break that consumer.
- `tests/monitoring/test_aggregate.py` — existing tests for `extract_kpis`/`summary_rows`; the structural pattern for the new test.

The buggy reader, `analysis/baseline_aggregate.py:171-176`:

```python
    # Emissions
    total_emissions = 0.0
    for hist in env_hist.values():
        series = hist.get("total_impact", [])
        if isinstance(series, list) and series:
            total_emissions += float(series[-1])
```

The writer, `instrumentation/waste_monitor.py:176-185` (read-only context — this is why `series` is per-timestamp):

```python
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            history["carbon_emissions"].append(0.0)
            history["transport_emissions"].append(0.0)
            history["landfill_emissions"].append(0.0)
            history["total_impact"].append(0.0)

        if impact_category in ["carbon_emissions", "transport_emissions", "landfill_emissions"]:
            history[impact_category][-1] += environmental_impact
            history["total_impact"][-1] += environmental_impact
```

There are three writers feeding this series, all passing per-event deltas: transport emissions (`core/collector.py:209`), processing emissions (`core/treatment.py:505`), landfill emissions (`utils/capacity_utils.py:183`).

Note for orientation: `baseline_aggregate.py` has two other `series[-1]` reads (lines 123 and 150). Those read **cumulative** series (`total_generated` totals and `processed.total`, which the monitor writes as running totals) and are CORRECT — do not touch them.

Repo conventions that apply: verbose variable names, no emojis, no magic numbers outside `config/constants.py`, surgical changes only. Test docstrings explain *which failure mode the test pins* — see the module docstring style in `tests/monitoring/test_aggregate.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full fast test suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass (249 passed, 6 skipped at planning time), ~15 s |
| Just the aggregate tests | `/mnt/c/Python313/python.exe -m pytest tests/monitoring/test_aggregate.py -q` | all pass |

Run from the repo root. The WSL system `python3` has no dependencies installed — always use `/mnt/c/Python313/python.exe`.

## Scope

**In scope** (the only files you should modify):

- `analysis/baseline_aggregate.py` (lines 171–176 only)
- `tests/monitoring/test_aggregate.py` (add one test)

**Out of scope** (do NOT touch, even though they look related):

- `instrumentation/waste_monitor.py` — changing the writer to cumulative would silently double-fix and break `visualization/temporal_comparison.py:146`, which sums the series.
- `analysis/baseline_aggregate.py` lines 123 and 150 — those `series[-1]` reads are over cumulative series and are correct.
- `visualization/temporal_comparison.py`, `analysis/pareto.py`, `visualization/policy_comparison_figure.py` — consumers; they need no change.
- Any regeneration of `outputs/` artifacts — that is the maintainer's decision (see Maintenance notes).

## Git workflow

- Branch: work directly on `main` is acceptable in this repo if the working tree is clean, but prefer `advisor/001-fix-emissions-kpi` if unsure.
- Commit message style (observed in `git log`): imperative, under 72 chars, no colon after the verb, body explains *why*. Example from history: `Remove always-zero generator cost series`. Suggested: `Fix total emissions KPI to sum the per-tick impact series`.
- Do NOT add a `Co-Authored-By` line. Do NOT push — the maintainer pushes.

## Steps

### Step 1: Write the pinning test (red first)

In `tests/monitoring/test_aggregate.py`, add:

```python
def test_total_emissions_sums_per_tick_impact_series_not_last_element():
    # track_environmental_impact appends a fresh 0.0 slot per new timestamp
    # (instrumentation/waste_monitor.py), so total_impact is per-tick, not
    # cumulative. Reading [-1] reports only the final tick's emissions.
    monitor_data = {
        "environmental_history": {
            "collector-1": {"total_impact": [10.0, 20.0, 30.0]},
            "treatment-1": {"total_impact": [5.0]},
        },
    }
    kpis = extract_kpis(monitor_data)
    assert kpis["total_emissions_kgco2e"] == 65.0
```

Check the exact KPI key name first: `grep -n "total_emissions" analysis/baseline_aggregate.py` — use whatever key `extract_kpis` returns (expected `total_emissions_kgco2e`). If `extract_kpis` requires more keys in `monitor_data` than shown above, mirror the minimal-dict style of the existing tests in this file (they pass sparse dicts; `extract_kpis` uses `.get` with defaults throughout).

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/monitoring/test_aggregate.py -q` → the new test FAILS (reports 35.0, the sum of last elements) while all pre-existing tests pass. A new test that passes immediately means you mis-targeted — STOP.

### Step 2: Fix the extraction

In `analysis/baseline_aggregate.py:176`, change:

```python
            total_emissions += float(series[-1])
```

to:

```python
            total_emissions += float(sum(series))
```

Also update the `# Emissions` comment (line 171) to note the series shape, e.g.:

```python
    # Emissions: total_impact is a per-timestamp series (the monitor appends a
    # fresh slot per new timestamp), so the run total is the sum, not the last
    # element -- unlike the cumulative processed/generated series above.
```

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/monitoring/test_aggregate.py -q` → all pass, including the new test.

### Step 3: Full suite

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass (250+ passed). If `tests/test_determinism.py` or mass-balance tests fail, STOP — they should be unaffected (this change touches only post-hoc KPI extraction, not the simulation).

## Test plan

- One new test in `tests/monitoring/test_aggregate.py` (Step 1): multi-entity, multi-tick `total_impact` series sums across both ticks and entities. The mutate-to-red sequencing in Steps 1–2 is the non-vacuity proof.
- Existing tests in the same file are the structural pattern.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `grep -n "series\[-1\]" analysis/baseline_aggregate.py` shows matches ONLY at the cumulative-series reads (the lines handling `total_generated`/`processed`, lines ~123 and ~150) — none in the emissions block
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpt at `analysis/baseline_aggregate.py:171-176` does not match the live code (drift).
- The new test passes BEFORE the fix is applied (you targeted the wrong code path).
- Any pre-existing test fails after the one-line change (the change must be observationally invisible to everything except the emissions KPI).
- You find another consumer that assumed the old last-element semantics (search: `grep -rn "total_emissions" --include='*.py' . | grep -v test`).

## Maintenance notes

- **The corrected KPI is much larger** (sum of ~hundreds of ticks vs the final tick). All previously generated artifacts under `outputs/` — `summary.csv`, `paired_comparison.csv`, dominance and Pareto reports, the Fig. 2 PDF — carry the old, wrong values and must be regenerated by re-running `python main.py --mode baseline --replications 100` before any number is cited. Report this plainly to the maintainer; do not regenerate outputs yourself (long-running, maintainer's call).
- The relative PUSH/PULL emissions ordering may change once the full-run total is used. That is a finding, not a regression — the maintainer values unfavorable numbers reported plainly.
- Reviewer scrutiny: confirm lines 123/150 (`series[-1]` over cumulative series) were left alone.
- Deferred follow-up: `visualization/policy_comparison_figure.py` scales emissions by `KG_PER_KILOTONNE = 1_000_000.0` with a comment saying raw values run ~1e6–2e7 kg; after the fix the axis range will shift — purely cosmetic, fix only if the figure looks wrong on regeneration.
