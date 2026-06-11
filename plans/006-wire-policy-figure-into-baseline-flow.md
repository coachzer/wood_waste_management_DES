# Plan 006: Regenerate the paper's Fig. 2 automatically at the end of each baseline scenario run

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- main.py visualization/policy_comparison_figure.py`
> If either file changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch,
> treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (additive, wrapped in the same warn-and-continue guard as its siblings)
- **Depends on**: none (but most valuable after plan 001 lands, since the figure plots the emissions KPI that 001 corrects)
- **Category**: direction
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

`visualization/policy_comparison_figure.py` produces the only simulation-derived figure the paper embeds (Fig. 2: emissions vs service level with 95% CI crosshairs, read from each combo's `summary.csv`). Today it must be run manually (`python -m visualization.policy_comparison_figure <scenario_dir>`) after every baseline run, while the paired-comparison, dominance, and Pareto reports already regenerate automatically at the end of `run_monte_carlo_baseline`. A figure that silently lags the latest run's numbers is a submission-stage credibility risk. The project's own ROADMAP names this exact wiring as the follow-up ("wire into main.py's baseline flow beside pareto/paired so it regenerates per run").

## Current state

- `visualization/policy_comparison_figure.py:187` — `def write_policy_comparison_figure(path, filename: str = "policy_comparison.pdf"):` — takes the scenario directory, reads each combo's `summary.csv` via `analysis.pareto.iter_combo_summaries`, writes a PDF with matplotlib's Agg backend (no browser engine), returns the written path (confirm the return convention by reading the function before wiring — the sibling writers return `None` when there is nothing to write).
- `main.py:182-212` — the post-scenario report block inside `run_monte_carlo_baseline`. Each writer is wrapped in its own `try/except Exception` that prints a `Warning: failed to write ...` line and continues — one broken report must not kill the batch. The Pareto block (ending at line ~212):

```python
        try:
            pareto_path = write_pareto_report(scenario_dir)
            if pareto_path is not None:
                print(f"Wrote Pareto frontier: {pareto_path}")
                # Parallel-coordinates HTML of the same frontier, beside the CSV.
                plot_path = write_pareto_plot(scenario_dir)
                if plot_path is not None:
                    print(f"Wrote Pareto frontier plot: {plot_path}")
        except Exception as e:
            print(f"Warning: failed to write Pareto frontier for {scenario_name}: {e}")
```

- Imports at the top of `main.py` already pull the sibling writers (e.g. `write_pareto_report`, `write_dominance_report`) — check the exact import block and match its style.
- matplotlib is required by the figure module; it is undeclared in `requirements.txt` until Plan 005 lands (it IS installed in the known-good `/mnt/c/Python313/python.exe` environment).

Each comment in that block states what the artifact adds beyond its siblings — match that style for the new block.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Import smoke | `/mnt/c/Python313/python.exe -c "import main"` | exit 0, no traceback |
| Figure module standalone (only if a populated scenario dir exists) | `/mnt/c/Python313/python.exe -m visualization.policy_comparison_figure outputs/baseline/Baseline` | prints the written PDF path |
| Full fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass |

Check for an existing populated scenario dir first: `ls outputs/baseline/ 2>/dev/null`. If none exists, skip the standalone command — do NOT run a full baseline to create one.

## Scope

**In scope**:

- `main.py` — one import line + one guarded block after the Pareto block

**Out of scope** (do NOT touch):

- `visualization/policy_comparison_figure.py` — it already works standalone; no signature changes.
- The grid-mode `main()` path — the figure needs Monte Carlo `summary.csv` CIs; grid mode has none.
- `analysis/` report writers.

## Git workflow

- Suggested message: `Regenerate policy comparison figure after each baseline scenario`.
- No `Co-Authored-By`. Do NOT push.

## Steps

### Step 1: Wire the call

In `main.py`, extend the imports beside the other report writers with `from visualization.policy_comparison_figure import write_policy_comparison_figure`, then append after the Pareto block (same indentation level):

```python
        # The paper's Fig. 2 (emissions vs service level with CI crosshairs)
        # reads the summary.csv files just written; regenerating it here keeps
        # the embedded figure in sync with the latest run's numbers.
        try:
            figure_path = write_policy_comparison_figure(scenario_dir)
            if figure_path is not None:
                print(f"Wrote policy comparison figure: {figure_path}")
        except Exception as e:
            print(f"Warning: failed to write policy comparison figure for {scenario_name}: {e}")
```

Adapt to the function's actual return convention as read in Step 0 (drift check): if it always returns a path, drop the `is not None` guard only if the siblings do — consistency with the surrounding block wins.

**Verify**: `/mnt/c/Python313/python.exe -c "import main"` → exit 0.

### Step 2: Standalone sanity (conditional)

If `outputs/baseline/<Scenario>/` with `summary.csv` files exists, run `write_policy_comparison_figure` against it via a one-liner and confirm a PDF lands in the scenario dir. Otherwise note "no populated scenario dir; verified by import + suite only" in the commit body.

**Verify**: PDF exists (`ls outputs/baseline/<Scenario>/policy_comparison.pdf`) — or the documented skip.

### Step 3: Full suite

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass.

## Test plan

No new test: the block is a guarded one-call wiring identical in shape to three adjacent blocks, and `tests/test_analysis_entry_points.py` plus the import smoke cover the import path. (A behavioral test would require a populated multi-combo scenario fixture — disproportionate for a warn-and-continue viz hook.)

## Done criteria

- [ ] `grep -n "write_policy_comparison_figure" main.py` → import + one call site inside `run_monte_carlo_baseline`
- [ ] The call is inside its own `try/except` printing a `Warning: ...` on failure (matching siblings)
- [ ] `/mnt/c/Python313/python.exe -c "import main"` exits 0
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `git status` clean except `main.py`, `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `write_policy_comparison_figure`'s signature differs from `(path, filename="policy_comparison.pdf")` (drift — re-read before wiring).
- Importing the figure module at `main.py` top level fails or measurably breaks anything (matplotlib import side effects) — if so, move the import inside the `try` block, mirroring how `analysis/pareto.py` lazily imports its plot writer, and say so in the commit body.

## Maintenance notes

- After Plan 001 lands and the baseline is re-run, this wiring is what guarantees Fig. 2 reflects the corrected emissions KPI without a manual step.
- Reviewer scrutiny: the new block must not be inside the Pareto `try` (one failing artifact must not suppress the other).
- The standalone CLI entry of `policy_comparison_figure` remains valid — this plan adds a second producer path, not a replacement.
