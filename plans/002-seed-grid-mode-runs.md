# Plan 002: Make grid-mode runs reproducible by passing an explicit seed

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- main.py config/constants.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

This repo's reproducibility contract (CLAUDE.md "Known Failure Modes") is that a given seed yields byte-identical run JSONs across separate process invocations, and the project maintains determinism backstop tests to defend it. But grid mode — the default `python main.py` invocation — calls `run_single_simulation` with no seed at all, so `SimulationManager(seed=None)` spawns entity RNGs from an unseeded `np.random.SeedSequence`. Every grid run produces different results, and any single-run figure or sanity check derived from grid mode cannot be reproduced or compared. The Monte Carlo baseline path is unaffected (it always passes `seed=base_seed + i`).

## Current state

Relevant file: `main.py` — CLI entry; `run_single_simulation` (line 21) and the grid loop in `main()` (line 252).

`main.py:36-45` — the seed handling inside `run_single_simulation`:

```python
    if seed is not None:

        random.seed(seed)
        np.random.seed(seed)

    try:
        scenario_config = get_scenario_config(scenario_name)

        manager = SimulationManager(seed=seed)
```

`main.py:252` — the grid-mode call site, inside the triple loop over scenarios × policies × strategies:

```python
                result = run_single_simulation(scenario_name, inventory_policy, stock_strategy)
```

No `seed` argument → `seed=None` → non-deterministic run.

The Monte Carlo path (`main.py:126` area) passes `seed=...` explicitly and is correct — leave it alone.

Seeding conventions (CLAUDE.md): per-entity RNGs are seeded via `np.random.SeedSequence` propagated `SimulationManager` → `FacilityBuilder` → each entity. Constants live in `config/constants.py` — no magic numbers elsewhere. Check whether a base-seed constant already exists: `grep -rn "base_seed\|BASE_SEED" main.py config/constants.py`. At planning time the Monte Carlo `base_seed` is a parameter of `run_monte_carlo_baseline` — reuse its default value as the grid seed so grid replication 0 matches Monte Carlo replication 0 of the same combo.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full fast test suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass (249 passed, 6 skipped at planning time) |
| Syntax check of main | `/mnt/c/Python313/python.exe -c "import ast; ast.parse(open('main.py').read())"` | exit 0, no output |

Run from the repo root. Always use `/mnt/c/Python313/python.exe` — the WSL `python3` has no deps.

Do NOT run a full grid simulation as verification — it is long-running and writes plots/outputs. The static checks plus the test suite are sufficient.

## Scope

**In scope** (the only files you should modify):

- `main.py` (the grid-loop call site in `main()`, and if needed a named constant)
- `config/constants.py` (only if you introduce a `GRID_MODE_SEED` constant — see Step 1)

**Out of scope** (do NOT touch):

- The Monte Carlo path (`run_monte_carlo_baseline`) — its seeding is correct.
- `core/simulation_manager.py` — the `SeedSequence` plumbing is correct; the gap is only at the grid call site.
- The `random.seed(seed)` / `np.random.seed(seed)` globals at `main.py:39-40` — possibly redundant with per-entity RNGs, but removing them is a behavior change to the Monte Carlo oracle. Leave them.

## Git workflow

- Commit message style: imperative, under 72 chars, no colon after the verb, body explains why. Suggested: `Seed grid-mode runs for reproducibility`.
- No `Co-Authored-By` line. Do NOT push.

## Steps

### Step 1: Determine the seed value to pass

Find the Monte Carlo default: `grep -n "base_seed" main.py`. Expected: `run_monte_carlo_baseline(..., base_seed=<N>, ...)` has a default value. Use that same `<N>` for grid mode. If the default is a literal in the function signature, add a module-level constant in `config/constants.py`:

```python
# Shared base seed: grid mode uses it directly; Monte Carlo replication i uses
# base + i (CRN), so a grid run reproduces MC replication 0 of the same combo.
DEFAULT_BASE_SEED = <N>
```

and reference it in both the `run_monte_carlo_baseline` default and the grid call. If `base_seed` already comes from a constant, just reuse that constant.

**Verify**: `grep -n "DEFAULT_BASE_SEED\|base_seed" main.py config/constants.py` → the grid path and MC default resolve to the same value.

### Step 2: Pass the seed at the grid call site

Change `main.py:252`:

```python
                result = run_single_simulation(
                    scenario_name, inventory_policy, stock_strategy,
                    seed=DEFAULT_BASE_SEED,
                )
```

(Match the import style at the top of `main.py` — it already imports from `config.constants`; extend that import rather than adding a new one.)

**Verify**: `/mnt/c/Python313/python.exe -c "import ast; ast.parse(open('main.py').read())"` → exit 0.

### Step 3: Full suite

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass.

## Test plan

No new automated test: a true reproducibility test for grid mode would re-run the full grid twice (minutes per run) — the existing `tests/test_determinism.py` already covers seeded-run determinism at the `run_single_simulation` level, and grid mode now goes through exactly that seeded path. Add nothing; state this reasoning in the commit body.

## Done criteria

- [ ] `grep -n "run_single_simulation(scenario_name, inventory_policy, stock_strategy)" main.py` → no matches (the unseeded call form is gone)
- [ ] Grid call site passes `seed=` resolving to the same value as the Monte Carlo `base_seed` default
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- `main.py:252` no longer matches the excerpt (drift).
- You cannot find a `base_seed` default in `run_monte_carlo_baseline` (the seeding scheme changed — the constant-unification step needs maintainer input).
- Any test fails after the change.

## Maintenance notes

- After this lands, two consecutive `python main.py` invocations should produce byte-identical run JSONs; if a future change breaks that, the unsorted-enum-set failure mode (CLAUDE.md) is the first suspect.
- A reviewer should check that only the grid path changed — the MC loop's `seed=base_seed + i` must be untouched.
- Deferred: deciding whether the global `random.seed`/`np.random.seed` calls at `main.py:39-40` are still needed (entities use their own `SeedSequence`-derived RNGs). Removing them risks shifting the determinism oracle; not worth it without a reason.
