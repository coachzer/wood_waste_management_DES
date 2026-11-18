# Implementation plans

The improve skill generated these plans on 2026-06-11 against commit `105eacc`. It ran a standard-depth audit over all nine categories and re-verified subagent findings against the code before planning. The session ran non-interactively, so it planned the highest-value findings by default. The maintainer should review this selection and can reject any plan by marking it REJECTED below.

Execute the plans in the order below unless the dependencies say otherwise. Each executor reads the plan fully before starting, honors its STOP conditions, and updates its row when done. The test command for everything is `.venv/bin/python -m pytest tests/ -q`. The Windows `python.exe` breaks on the `plots` symlink.

## Execution order and status

| Plan | Title | Priority | Effort | Depends on | Status |
| ---- | ----- | -------- | ------ | ---------- | ------ |
| 001 | Fix total_emissions_kgco2e to sum the per-tick impact series | P1 | S | none | DONE (merged into `main` as `219d81d`; red-to-green pinning test verified; reviewed and approved 2026-06-11. Emissions numbers in outputs/ grow by orders of magnitude, so re-run the baseline before citing them) |
| 005 | Declare scipy/matplotlib/pytest deps; fix stale README paths | P1 | S | none | DONE (merged into `main` as `c07840e` + `0d50035` via merge commit `5dbde81`; reviewed and approved 2026-06-11) |
| 003 | Characterization tests: generator overflow + cross-region double-count guard | P1 | M | none | DONE (merged into `main` as `83860e0`; reviewed and approved 2026-06-11) |
| 002 | Seed grid-mode runs for reproducibility | P2 | S | none | DONE (merged into `main` as `a522537`, a cherry-pick of `536aa17`; full suite 258 passed + 6 skipped, re-verified after the merge; reviewed and approved 2026-06-11) |
| 004 | Cap per-type generation at storage headroom (was all-or-nothing drop) | P2 | S | 003 | DONE (merged into `main` as `e08cbf9`; reviewed and approved 2026-06-11. outputs/ is now stale, so re-run the baseline before citing numbers) |
| 006 | Regenerate the paper's Fig. 2 in the baseline flow | P3 | S | none (best after 001) | DONE (merged into `main` as `87e76ad`; behavioral check regenerated the figure from the Baseline summary.csv files and wrote a valid PDF; reviewed and approved 2026-06-11) |
| 007 | Parallelize Monte Carlo baseline replications across worker processes | P2 | M | none | DONE (worker pool support added in `main.py`, `--workers` CLI wired, parallel determinism regression test added; full suite 258 passed + 7 skipped, smoke artifacts byte-identical) |
| 008 | Route treatment kanban signals to their intended region | P2 | S | none | DONE (reviewed and approved 2026-06-11; merged into `main` as `70a51ee`, with the ADR 0018 addendum in `114e59f`; 3 routing tests in `tests/core/test_kanban_signal_routing.py`) |
| 009 | RunPaths module: Run Name slug, manifest writer, LATEST pointer | P1 | M | none | TODO |
| 010 | Baseline mode writes per-run directories (manifest, kpis.csv, gzipped raw, figures/) | P1 | L | 009 | TODO |
| 011 | Cross-run comparison CLI reading kpis.csv and manifests | P2 | M | 009, 010 | TODO |

Plans 009-011 were added on 2026-06-11 against commit `566a59e` via `improve plan`. They reorganize the outputs at the user's direction, with no audit pass. They implement the **Run** and **Run Name** convention that CONTEXT.md documents but the code does not yet have. Every baseline invocation would land in its own `outputs/runs/{slug}/` directory with a `manifest.json`, a tidy `kpis.csv`, gzipped raw sidecars, and a `figures/` subdirectory. Plan 011 adds the first cross-run comparison tool. The three run strictly in sequence: 009, then 010, then 011. **Before executing 010**, note that `main.py` carried an uncommitted change at planning time (KPI-family figure wiring) that the plan's excerpts include. Commit it first. The maintainer decided that the legacy `outputs/baseline/` tree stays frozen in place. Nothing writes to it again and nothing deletes it.

Plans 001-008 are all merged into `main`. Plan 008 was cherry-picked from its worktree branch as `70a51ee` and `114e59f`, and the plan-execution worktrees and branches have been removed. Plans 009-011 have not been started, so no `outputs/runs/` code exists yet. Remember that `outputs/` predates plans 001 and 004. Re-run `python main.py --mode baseline --replications 100` before citing any number. The wired Fig. 2 regenerates automatically.

Status values: TODO | IN PROGRESS | DONE | BLOCKED (with one-line reason) | REJECTED (with one-line rationale)

## Dependency notes

- 004 requires 003. Plan 003 pins the current generator semantics, and plan 004 deliberately flips one of those tests. The red-to-green flip documents the semantic change. If 004 runs first, 003's executor pins the new capped behavior instead, and its STOP conditions cover this.
- 006 is independent, but it pays off fully only after 001, because the figure plots `total_emissions_kgco2e`, which 001 corrects.
- **After 001 and 004 land, all `outputs/` artifacts are stale.** The maintainer must re-run `python main.py --mode baseline --replications 100` before citing any number. The emissions KPI grows by orders of magnitude (001), and the collection-rate and holding-cost KPIs shift (004). Both plans say so in their maintenance notes. The shift comes from fixing real bugs and is not a regression.

## Audited but not planned (backlog, worth a future plan if the maintainer wants it)

- ~~**Parallelize Monte Carlo replications**~~. Promoted to plan 007 on 2026-06-11.
- ~~**Raw-history JSON writes block the replication loop**~~. Plan 010 partly addresses this: it gzips the raw sidecars (about 10:1) and adds a `--no-raw` opt-out. Moving the writes to a writer thread remains open if write time still matters after gzip.
- **Grid-mode relocation onto RunPaths**, deferred from the 009-011 reorganization. Move grid-mode output off `plots/` into `outputs/runs/grid_*__HHMM/`, remove the `os.makedirs(PLOTS_ROOT)` side effect from `WasteMonitor.__init__`, give `ScenarioComparison` an `output_dir` parameter, and move the GIS strays out of `data/viz/output/`. Blocked until 010 lands. First check whether grid mode is still a publication path at all (see the temporal_comparison note below).
- **Figures for unplotted KPI families**, deferred from the reorganization. These are a cost-component stack (including holding cost, see direction finding 2), availability, volumes and throughput rates, and the lost-sales split (`no_capability` vs `stockout`). Follow the `kpi_family_figures.py` pattern. They are cheap once 010's `figures/` layout exists.
- **Retire the frozen legacy tree.** Once the first new-style 100-replication refresh lands and the paper's figures are regenerated from it, delete `outputs/baseline/` and the readers in `.scratch/paper-draft-audit/` in one sweep.
- ~~**Shared KanbanManager signal bus, investigate but do not fix**~~. Investigated on 2026-06-11 and documented in ADR 0018. The deferred signal-loss fix was **promoted to plan 008** (region routing of treatment signals). The kanban bus is load-bearing, because it gates PULL collector behavior and is not dead code. It is also lossy, because of the cross-region unconditional ack at `collector.py:471`. Flow-based metrics are unaffected.
- **`OperationalEntity._failure_counts` is a class-level mutable shared across instances.** Only `SimulationManager.__init__` resets it (`models/data_classes.py:18`). It affects only the diagnostic failure printout, but it makes tests order-sensitive if they construct entities directly. The fix is small (S): make it an instance variable.
- **Expansion-event KPI accounting in `core/collector.py:311-336`.** The two-phase overflow handler records the pre-expansion overflow amount on the expand branch while it force-landfills a different residual. Mass balance is intact, but the `expansion_volume_m3` event bookkeeping may be inconsistent. Confidence is medium, so trace one expand event before planning a fix.
- **Collector god object** (`core/collector.py`, 799 lines, 30 methods). A first slice would extract the vehicle-dispatch concern into a `CollectorTransport` helper. The effort is L, and it conflicts with the surgical-changes convention unless the maintainer explicitly agrees.
- **More untested code.** This covers the collector dispatch chain (`_process_kanban_signals`, `collect_from_generator`), the `main.py` seams (`_write_combo_summary`, the warn-and-continue batch loop), and `visualization/temporal_comparison.py` (703 lines, zero tests). For the last one, also check whether the grid-mode-only `ScenarioComparison` path is still a publication path at all.
- **Rename `tests/monitoring/` to `tests/analysis/`**, because the `monitoring/` source package it mirrored was deleted. Small (S) and cosmetic.
- **Developer tooling.** Add a `pyproject.toml` with `[tool.pytest.ini_options]`, a ruff config, and a 20-line GitHub Actions CI (this needs plan 005's requirements fix first). A lockfile is optional.

## Direction findings (research options for the maintainer to decide, not defaulted into plans)

These are paper-level or PhD-level options grounded in evidence from the repo. Each would become a design or spike plan on request.

1. **Run the stress scenarios into the paper.** SupplyDisruption and GenerationSurge are fully wired and anchored to calibration sources (`config/base_config.py:108-129`), but `paper-draft/05-results.md` has no cross-scenario robustness section. Two `--mode baseline --scenario <X>` runs plus a §5.6 would answer the reviewer question that is sure to come about how robust the PUSH/PULL ordering is.
2. **Surface holding cost** (ADR 0017). The first cost component that is policy-sensitive by design has no figure (`kpi_family_figures.py` lacks it) and does not appear in the paper. It needs one line in the metrics list and a §5.2 paragraph with the caveat that the rate is a placeholder.
3. **Run the sensitivity analysis the paper already promises** (`paper-draft/todo.md:267`). Start with the bounds on the avoided-emissions factors, which is pure post-hoc arithmetic over the existing `run_*.json` files (ADR 0011 names the four source papers). Sweeps over carbon price and holding cost need new runs.
4. **Resolve the "Lebanon paper" landfill-cost citation** (`config/base_config.py:26`, flagged red in `paper-draft/todo.md:139`). Swap it for the citable CEWEP/EEA figure that the currency-consistency issue already names. The full EUR restatement stays after the paper, per ROADMAP.
5. **Redesign the bullwhip metric** (`.scratch/bullwhip/issues/13`), with downstream-throughput anchoring and a bin-width sweep. This is a spike the size of a PhD chapter and would supersede ADR 0004. It is not an item for the current paper.

## Findings considered and rejected

- **Cross-region "requested counts as satisfied" timing.** Treatment deducts `remaining` when the transport departs, not when it arrives. The docstring at `core/treatment.py:560` documents exactly this behavior as an ADR 0009 design choice. It is not a bug, and at most deserves a sentence in the paper's limitations.
- **The lazy visualization import in `analysis/pareto.py` as a layering violation.** The lazy `try/except` import inside the CLI block is the standard way to break an import cycle, and a comment says it degrades gracefully by design. Not worth doing.
- **The `current_storage` property recomputing a dict sum on the monitor path.** This is a micro-optimization. Summing a dict of about 14 keys a few times per tick costs almost nothing next to the simulation itself. Not worth doing.
- **Stochastic-dominance FSD/SSD flag logic.** It was audited twice for suspected sign errors. The interleaved flag updates are correct, and the auditor's own trace confirmed both orders. No change is needed, though the non-obvious `if/elif` interleaving would merit a comment if the file is ever touched anyway.
- **Bias from the flat backward extrapolation in Little's Law.** The first monitor sample lands at t=0, so the suspected bias between zero and the first sample covers no time at all. No bug.
- **Upper-bound pins or a lockfile as a requirement.** This is a solo research repo with one known-good interpreter. The version floors and declared dependencies from plan 005 cover the real failure. A lockfile stays in the optional backlog.
