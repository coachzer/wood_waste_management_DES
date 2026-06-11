# Plan 007: Parallelize Monte Carlo baseline replications across worker processes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8592fe4..HEAD -- main.py tests/test_determinism.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (all of plans 001–006 are already merged into `main`)
- **Category**: perf
- **Planned at**: commit `8592fe4`, 2026-06-11

## Why this matters

`python main.py --mode baseline --replications 100` runs 600 simulations
(100 replications x 6 policy/strategy combos) strictly sequentially in one
process. Because seeding uses Common Random Numbers — replication `i` always
gets `seed = DEFAULT_BASE_SEED + i`, fully re-seeded per replication — every
replication is independent and the loop is embarrassingly parallel. Recent bug
fixes (plans 001 and 004) invalidated all existing `outputs/` numbers, so full
baseline re-runs are now frequent; a process pool turns a multi-hour batch into
a fraction of that wall-clock on a typical 8-core machine. The hard constraint
is reproducibility: the parallel path must produce **byte-identical** artifacts
(`run_*.json`, `raw_*.json`, `summary.csv`) to the sequential path, and the
default behavior with no new flag must be exactly today's behavior.

## Current state

Relevant files:

- `main.py` — the only file with the replication loop. `run_single_simulation`
  (lines 22–79) seeds globals and runs one simulation;
  `run_monte_carlo_baseline` (lines 82–228) holds the sequential triple loop;
  the `argparse` block (lines 299–335) defines the CLI.
- `tests/test_determinism.py` — existing cross-process byte-identity guard;
  its `_run_baseline` helper (lines 25–48) invokes `main.py` as a subprocess.
  Your new test goes here, following the same pattern.
- `tests/conftest.py` — registers the `slow` marker and the `--run-slow`
  opt-in flag. Do not modify; just mark your test `@pytest.mark.slow`.

Why processes, not threads (do not change this decision):

- `run_single_simulation` calls `random.seed(seed)` and `np.random.seed(seed)`
  — process-global state (main.py:40-41).
- `SimulationState` is a singleton reset via `SimulationState._instance = None`
  in `SimulationManager.__init__()` — one live simulation per process, ever.
- The project interpreter is **Windows Python 3.13** at
  `/mnt/c/Python313/python.exe` (the WSL `python3` has no deps). Windows
  multiprocessing uses the **spawn** start method: the worker function must be
  a module-level function in `main.py`, all task arguments must be picklable,
  and the existing `if __name__ == "__main__":` guard (present, line 299) is
  what makes spawn re-import safe. The repo enums pickle fine (by name).

The sequential inner loop as it exists today (`main.py:119-181`, abbreviated):

```python
        for policy in inventory_policies:
            for strategy in stock_strategies:
                print(f"\n-- {policy.value} x {strategy.value} --")
                combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
                combo_dir.mkdir(parents=True, exist_ok=True)
                combo_kpis: list[dict] = []
                for i in range(replications):
                    seed = base_seed + i
                    res = run_single_simulation(
                        scenario_name=scenario_name,
                        inventory_policy=policy,
                        stock_strategy=strategy,
                        seed=seed,
                        create_mfa=False,
                        raise_on_violation=False,
                    )
                    results.append(res)
                    kpis = extract_kpis(res["monitor_data"])
                    combo_kpis.append(kpis)
                    # Persist per-run KPIs (avoid raw monitor_data with Enums)
                    run_path = combo_dir / f"run_{i:03d}.json"
                    try:
                        with open(run_path, "w", encoding="utf-8") as f:
                            json.dump({... "kpis": kpis}, f, separators=(",", ":"))
                    except Exception as e:
                        print(f"Warning: failed to write {run_path}: {e}")
                    raw_path = combo_dir / f"raw_{i:03d}.json"
                    try:
                        with open(raw_path, "w", encoding="utf-8") as f:
                            json.dump(jsonify(build_raw_payload(res["monitor_data"])),
                                      f, separators=(",", ":"))
                    except Exception as e:
                        print(f"Warning: failed to write {raw_path}: {e}")

                print(f"Completed {replications} reps for {policy.value} x {strategy.value}")
                summary_csv = combo_dir / "summary.csv"
                try:
                    _write_combo_summary(summary_csv, combo_kpis)
                ...
```

After the combo loops, four per-scenario reports run against `scenario_dir`
(`write_paired_comparison_report`, `write_dominance_report`,
`write_pareto_report` + plot, `write_policy_comparison_figure`,
main.py:183-223). These read the `run_*.json` / `summary.csv` files just
written, so they MUST run only after every replication task for that scenario
has completed. Do not parallelize or reorder them.

Facts verified during planning (rely on them):

- Nothing consumes `run_monte_carlo_baseline`'s return value: the only caller
  is the `__main__` block, which discards it (`_ = run_monte_carlo_baseline(...)`,
  main.py:329). No test imports it (`grep -rn "run_monte_carlo_baseline" tests/`
  matches nothing). You may therefore stop accumulating full `monitor_data`
  result dicts in the parent and return lightweight per-replication records
  instead — required, because shipping `monitor_data` over IPC would be the
  dominant cost.
- One test imports `run_single_simulation` (`tests/monitoring/test_mass_balance.py:318`).
  Do not change `run_single_simulation`'s signature or behavior.
- `extract_kpis` returns a plain JSON-serializable dict (it is `json.dump`ed
  into `run_*.json` today) — safe to pickle back from a worker.
- A failed replication today raises `SystemExit` from `run_single_simulation`'s
  `except` block and aborts the whole batch. `concurrent.futures` propagates
  worker `BaseException`s (including `SystemExit`) through `future.result()`,
  so calling `.result()` in the parent preserves abort-the-batch semantics
  without extra code.

Repo conventions that apply:

- Verbose descriptive variable names (`replication_index`, not `idx`).
- No emojis in code or comments.
- Surgical changes only — do not refactor `run_single_simulation`, the grid
  `main()` path, or the report-writing block while in the file.
- Comment style: short, explains *why* (see the existing comments in the loop
  above). Match it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full test suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass (258+ passed, ~6 skipped), exit 0 |
| New slow test only | `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow -k parallel` | 1 passed |
| Smoke run, sequential | `/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --out-root .scratch/plan007_seq` | exit 0, 12 `run_*.json` written |
| Smoke run, parallel | `/mnt/c/Python313/python.exe main.py --mode baseline --scenario Baseline --replications 2 --workers 4 --out-root .scratch/plan007_par` | exit 0, identical artifact set |
| Compare artifacts | `diff -r .scratch/plan007_seq .scratch/plan007_par` | no output, exit 0 |

Note: all commands must use `/mnt/c/Python313/python.exe`. The WSL `python3`
has no dependencies installed and will fail at import.

## Scope

**In scope** (the only files you should modify):

- `main.py`
- `tests/test_determinism.py`
- `plans/README.md` (status row only — skip if your dispatcher maintains the index)

**Out of scope** (do NOT touch, even though they look related):

- `run_single_simulation` and the grid-mode `main()` function — grid mode
  stays sequential; the mass-balance test imports `run_single_simulation`.
- `core/simulation_manager.py`, `config/constants.py`, any `analysis/` or
  `visualization/` module — the per-scenario report block in
  `run_monte_carlo_baseline` is called exactly as before.
- `CLAUDE.md` / `README.md` — the maintainer has uncommitted local edits;
  documentation of `--workers` is deferred (see Maintenance notes).
- Worker stdout suppression or log capture — interleaved worker prints in
  parallel mode are accepted; do not redirect or silence them.

## Git workflow

- Branch: `advisor/007-parallelize-monte-carlo-replications`
- Commit style: imperative mood, under 72 chars, no colon after the verb,
  body (after a blank line) explains *why* (example from log:
  `Seed grid-mode runs for reproducibility`). Do NOT add a `Co-Authored-By`
  line.
- Do not push or open a PR.

## Steps

### Step 1: Extract a module-level replication worker in `main.py`

Add a top-level function (module level is mandatory for Windows spawn
pickling) above `run_monte_carlo_baseline`:

```python
def _run_baseline_replication_task(
    scenario_name: str,
    inventory_policy: InventoryPolicy,
    stock_strategy: StockStrategy,
    seed: int,
    replication_index: int,
    combo_dir: Path,
) -> dict:
    """Run one baseline replication and persist its artifacts.

    Module-level so it pickles under the Windows spawn start method. Artifact
    writes (run_NNN.json, raw_NNN.json) happen here, inside the worker, so the
    bulky monitor_data never crosses the process boundary -- only the small
    KPI dict returns to the parent.
    """
```

Body: move the existing per-replication code verbatim from the inner loop —
the `run_single_simulation(...)` call (with `create_mfa=False`,
`raise_on_violation=False`), `extract_kpis`, the `run_{i:03d}.json` write
(same dict shape, same `separators=(",", ":")`), and the `raw_{i:03d}.json`
write including both existing comments and both warn-and-continue
`try/except` blocks. Return a lightweight record:

```python
    return {
        "base_scenario": simulation_result["base_scenario"],
        "scenario_name": simulation_result["scenario_name"],
        "inventory_policy": simulation_result["inventory_policy"],
        "stock_strategy": simulation_result["stock_strategy"],
        "seed": simulation_result["seed"],
        "replication_index": replication_index,
        "kpis": kpis,
    }
```

**Verify**: `/mnt/c/Python313/python.exe -c "import main; print(main._run_baseline_replication_task.__name__)"`
→ prints `_run_baseline_replication_task`, exit 0.

### Step 2: Rewire `run_monte_carlo_baseline` to dispatch tasks

Add a `workers: int = 1` keyword parameter. Update the docstring to state the
return value is now a list of lightweight per-replication records (no
`monitor_data`) and that `workers > 1` uses a process pool with byte-identical
artifacts.

Inside the per-scenario block, replace the inner triple loop body:

1. Build the flat, deterministically ordered task list first (this also
   creates the combo directories, exactly as today):

```python
        replication_tasks: list[tuple] = []
        for policy in inventory_policies:
            for strategy in stock_strategies:
                combo_dir = scenario_dir / f"{policy.value}__{strategy.value}"
                combo_dir.mkdir(parents=True, exist_ok=True)
                for replication_index in range(replications):
                    replication_tasks.append(
                        (scenario_name, policy, strategy,
                         base_seed + replication_index, replication_index, combo_dir)
                    )
```

2. Execute. `workers == 1` must run the worker function inline in task order —
   no pool, no executor import side effects — so the default path is the
   current behavior:

```python
        if workers <= 1:
            replication_records = [
                _run_baseline_replication_task(*task) for task in replication_tasks
            ]
        else:
            # CRN replications are independent (each worker re-seeds from its
            # own seed), so the pool only changes wall-clock, never artifacts.
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(_run_baseline_replication_task, *task)
                    for task in replication_tasks
                ]
                # .result() re-raises worker failures (including SystemExit),
                # preserving the sequential abort-the-batch semantics.
                replication_records = [future.result() for future in futures]
```

   Import `ProcessPoolExecutor` from `concurrent.futures` at the top of
   `main.py` with the other imports.

3. Group records per combo, sort by `replication_index`, append to `results`,
   and write each combo's `summary.csv` via the existing `_write_combo_summary`
   inside the existing warn-and-continue `try/except`, keeping the existing
   `print(f"Completed {replications} reps for ...")` line per combo. Iterate
   combos in the same `inventory_policies` x `stock_strategies` order as
   today so stdout and CSV write order are unchanged in sequential mode.
   Because `futures` is built in task-list order and the list comprehension
   gathers in that same order, `replication_records` is already in
   deterministic order — the per-combo sort is a guard, not a fix.

4. The per-scenario report block (paired comparison, dominance, Pareto,
   policy figure) stays exactly where it is, after all combos of the scenario
   are summarized.

Do NOT create the pool once across scenarios vs per scenario based on your
own judgment: create it once per scenario (inside the scenario loop, around
that scenario's task list) so reports never race tasks. Worker processes are
reused within a scenario, which is where the volume is.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass
(the fast suite does not exercise baseline mode, so this checks imports and
collaterals only — the real gates are steps 4–5).

### Step 3: Add the `--workers` CLI flag

In the `argparse` block:

```python
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Worker processes for baseline replications (default 1 = sequential). "
        "Artifacts are byte-identical at any worker count; only wall-clock changes.",
    )
```

Pass `workers=args.workers` in the `run_monte_carlo_baseline(...)` call.
Grid mode ignores the flag (do not wire it into `main()`).

**Verify**: `/mnt/c/Python313/python.exe main.py --help` → output includes
`--workers`, exit 0.

### Step 4: Smoke-compare sequential vs parallel artifacts

Run the two smoke commands from the command table (sequential into
`.scratch/plan007_seq`, parallel `--workers 4` into `.scratch/plan007_par`),
then `diff -r` the two trees.

**Verify**: `diff -r .scratch/plan007_seq .scratch/plan007_par` → empty
output, exit 0. Every `run_*.json`, `raw_*.json`, `summary.csv`, and report
file must be byte-identical. If the diff is non-empty, the divergence is a
bug in your wiring (most likely combo grouping or record ordering) — fix and
re-run; if it fails twice, STOP.

### Step 5: Add the parallel-determinism regression test

In `tests/test_determinism.py`:

1. Extend the existing `_run_baseline` helper with keyword parameters
   `workers: int = 1` and `replications: int = 1`, appending
   `"--workers", str(workers)` and substituting the replications value into
   the existing argument list. Existing callers pass no new arguments and
   must behave identically.
2. Add, following the structure of
   `test_baseline_runs_are_byte_identical_across_processes` (same
   `@pytest.mark.slow`, same `rglob` + `read_bytes` comparison):

```python
@pytest.mark.slow
def test_parallel_baseline_matches_sequential_byte_for_byte(tmp_path):
    """--workers N must change wall-clock only, never artifacts.

    CRN replications are independent (each fully re-seeded), so a process
    pool must reproduce the sequential run exactly. Compares every run_*.json,
    raw_*.json, and summary.csv byte-for-byte between a sequential and a
    parallel invocation of the same 2-replication Baseline batch.
    """
```

   Run `_run_baseline(out_seq, workers=1, replications=2)` and
   `_run_baseline(out_par, workers=4, replications=2)`, then compare the
   sorted `rglob` sets for each of the three patterns (`run_*.json`,
   `raw_*.json`, `summary.csv`): identical relative-path lists, then
   byte-equal contents, with an assert that the `run_*.json` list is
   non-empty (guards against a silent zero-file pass). Per the project's
   test standard, verify the test is non-vacuous: temporarily break the
   grouping (e.g. reverse `replication_records` before the combo grouping),
   confirm the test fails, then restore.

**Verify**:
`/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow -k parallel`
→ `1 passed`.

### Step 6: Full suite and cleanup

Delete the `.scratch/plan007_seq` and `.scratch/plan007_par` smoke
directories. Run the full fast suite one final time.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass,
exit 0; `git status` shows only `main.py` and `tests/test_determinism.py`
modified.

## Test plan

- New test: `tests/test_determinism.py::test_parallel_baseline_matches_sequential_byte_for_byte`
  (slow, opt-in) — the load-bearing regression guard for this plan. Covers:
  artifact-set equality, byte equality of `run_*.json` / `raw_*.json` /
  `summary.csv`, multi-replication-per-combo accumulation order.
- Pattern: `test_baseline_runs_are_byte_identical_across_processes` in the
  same file.
- Existing slow determinism tests still pass unchanged (they call the
  default sequential path):
  `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow`
  → 3 passed (2 existing + 1 new). Run this once if time allows; the `-k
  parallel` gate in step 5 is the mandatory one.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py -q --run-slow -k parallel` → 1 passed
- [ ] `/mnt/c/Python313/python.exe main.py --help` lists `--workers`
- [ ] Step 4's `diff -r` of sequential vs parallel smoke trees was empty
- [ ] `git status` in the worktree shows changes only to `main.py` and
      `tests/test_determinism.py` (plus `plans/README.md` if you maintain it)
- [ ] No change to `run_single_simulation`'s signature:
      `git diff main -- main.py | grep "def run_single_simulation"` → no match

## STOP conditions

Stop and report back (do not improvise) if:

- The drift check shows `main.py` or `tests/test_determinism.py` changed
  since `8592fe4` and the "Current state" excerpts no longer match.
- Step 4's artifact diff is non-empty after one fix attempt — byte-identity
  is the plan's contract; do not ship "close enough" or weaken the comparison.
- `ProcessPoolExecutor` fails on spawn with a pickling error or an import
  error inside the worker (e.g. `main.py` module import has a side effect
  under spawn re-import). That invalidates the worker-in-`main.py` approach;
  report the traceback rather than relocating the worker to a new module on
  your own.
- The parallel smoke run is not faster AND produces different artifacts —
  but note: on a 2-replication smoke it may legitimately be *slower* than
  sequential (spawn + import overhead per worker dominates). Slower-but-
  identical is fine; do not "optimize" in response.
- Fixing anything appears to require touching `run_single_simulation`,
  `core/`, `analysis/`, or `visualization/`.

## Maintenance notes

- `run_monte_carlo_baseline` now returns lightweight records without
  `monitor_data`. Anything that later wants in-process access to full
  histories must read the `raw_*.json` sidecars instead (that is what they
  are for).
- Reviewer should scrutinize: (a) the gather order feeding `combo_kpis` —
  `summary.csv` row order must be replication order; (b) that the worker
  writes use the exact same JSON shape/separators as before; (c) that the
  new test actually compares bytes, not just file counts.
- Deferred, deliberately: documenting `--workers` in `CLAUDE.md`/`README.md`
  (maintainer has uncommitted edits there — they should add a line like
  `python main.py --mode baseline --replications 100 --workers 8` after
  merging); a `--save-raw` opt-out for the `raw_*.json` writes (separate
  backlog item); parallelizing grid mode (low value, 6 runs).
- If a future change makes replications non-independent (e.g. antithetic
  pairs sharing state), the pool becomes invalid — the determinism test will
  catch the artifact divergence.
