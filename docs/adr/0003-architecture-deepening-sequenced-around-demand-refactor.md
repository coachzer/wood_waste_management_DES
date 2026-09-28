# Architecture deepening, sequenced around the demand refactor

> NOTE (2026-06-07): this ADR records a *plan* in present and future tense, and most of it is now history.
> Candidate 1 (inline the `*_utils.py` modules) and the demand refactor (ADR 0002) landed. **Candidate 2
> (replace the `SimulationState` singleton with injected state) was NOT adopted.** The singleton and its
> `_instance = None` reset in `SimulationManager.__init__()` remain the live mechanism (see CLAUDE.md
> "Known Failure Modes"). The "optional-before / deferred" status of Candidates 2 and 4-6 is therefore
> resolved, not pending. The referenced scratch artifacts (`.scratch/NEXT-SESSION-demand-refactor.md`,
> `.scratch/architecture-deepening/PRD.md`) may have been archived or moved since. **Where the code and git
> history disagree with this prose, trust the code and git history.** The body keeps its original meaning
> under the append-only doc rule.

An architecture review (2026-05-22, archived as `Architecture review — wood_waste_management_DES.htm` and captured in `.scratch/architecture-deepening/PRD.md`) applied Ousterhout's *A Philosophy of Software Design* to the codebase (about 5,600 LOC, 35 files). It found six structural weaknesses:

- three shallow `*_utils.py` modules that move complexity around instead of reducing it;
- a `SimulationState` singleton coupling 20+ call sites to global mutable state;
- stock-strategy logic scattered across 5 locations with duplicated thresholds;
- two parallel entity hierarchies that need manual field mapping;
- five thin initialization modules;
- pure decision logic inside SimPy generators, which cannot be tested without a full simulation.

None are bugs. They cost testability and extensibility.

The complication is that the other large open work item, the demand-model refactor (ADR 0002), rewrites many of the same files (`state.py`, `treatment.py`, `simulation_manager.py`) and changes behavior on purpose. So the decision covers both *what* to refactor and *in what order relative to the demand refactor*, because the wrong order means doing the same work twice.

We will deepen the architecture in a hybrid order. First the one candidate that helps the demand refactor, then the demand refactor, then the candidate that the demand refactor would otherwise force us to redo.

## Considered options

- **Full architecture first (all of Phase 1, then the demand refactor).** This gives the cleanest codebase going into the refactor. Rejected because Candidate 3 (strategy extraction) consolidates the exact stock-strategy logic the demand refactor rewrites. Signal volume becomes `S = capacity`, the `on_demand_buffer_ratio` / `on_demand_target_ratio` constants become dead code, and PULL signaling moves from a fixed 10% threshold to a strategy-aware one. Extracting strategies into protocol classes against the current semantics and then rewriting those classes right away is wasted effort.
- **Demand refactor first, architecture later.** This gets to research value fastest, since the demand refactor is the methodological contribution that feeds the papers and the architecture work produces no new figures. Rejected as the sole plan because the demand refactor is large and changes behavior, and it is much easier to implement and debug on the inlined single-module codebase that Candidate 1 produces. We keep its priority on research value by doing only the cheap, helpful refactor first.
- **Hybrid (chosen).** Candidate 1 (inline utils) now, then the demand refactor, then Candidate 3 (strategy modules) with its final semantics. Candidate 2 (dependency injection) is optional-before, done first only if the demand refactor's mass-balance tests want the no-singleton test seam early. Candidates 4-6 are evaluated after Phase 1, as the review recommends.

## Key decisions within this design

- **Candidate 1 (inline `*_utils.py`) is the immediate next step.** Inline `generator_utils.py`, `collector_utils.py` and `treatment_utils.py` back as methods on `WasteGenerator`, `CollectorCompany` and `TreatmentOperator`. This is pure locality. It survives any later behavior change. It shrinks the set of files the demand refactor touches to one per entity instead of two (the refactor touches `treatment_utils.py::fulfill_demand` anyway). And it can be verified against the current git baseline before that baseline shifts. Accepted tradeoff: `treatment.py` grows to about 1030 LOC. The review endorses this, since for a single deep module locality matters more than file size.
- **Candidate 3 (strategy/policy modules) is deferred until after the demand refactor.** Extract `StockStrategy` and `InventoryPolicy` as protocol classes once, against the post-refactor semantics, so the consolidation uses the rules that will actually ship.
- **Candidate 2 (replace the singleton with injected state) is optional-before.** It provides the test seam the demand refactor's mass-balance tests want (no `_instance = None` reset ritual). It changes how state is wired, which is independent of the demand refactor's rewrite of what state *contains*, so the rebase is modest. Do it before the demand refactor only if the test seam is wanted early. Otherwise do it after.
- **Candidates 4 (merge entity hierarchies), 5 (deepen FacilityBuilder) and 6 (separate SimPy from decisions) stay deferred.** Re-evaluate them after Phase 1, as the review recommends. Candidate 6 may become unnecessary once Candidate 3 extracts the strategy patterns.
- **The validation gate is behavior preservation.** Each architecture candidate must leave simulation outputs identical. Run `main.py --mode baseline --replications 10`, compare KPIs (total waste, costs, demand satisfaction) within floating-point tolerance, and check for new tracebacks. This gate only works against the *current* baseline, which is another reason to land the behavior-preserving refactors that precede the demand refactor while that baseline still holds.

## Consequences

- Candidate 1 deletes three files (about 488 LOC of shallow wrappers) and updates their call sites (e.g., `generator.py` for `handle_overflow`, `collector.py` for completed-transport handling). There is no architectural redesign. Functions move, and their signatures collapse into `self.` access.
- The demand refactor (ADR 0002) starts on the inlined codebase, so the file references in `.scratch/NEXT-SESSION-demand-refactor.md` that point to `*_utils.py` now mean the owning modules.
- `.scratch/architecture-deepening/PRD.md` stays the operational issue list. This ADR records the decision and the sequencing rationale. The review HTML is the source artifact.
