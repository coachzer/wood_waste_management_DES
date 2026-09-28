# Treatment-echelon inbound flow is collector intake, not the cross-region transport log

> NOTE (2026-09-28): the verification record this ADR cites, `docs/adr/0009-finding-b-verification.md`,
> was deleted on purpose in `2a48904` (2026-06-09). That commit called it a throwaway record that
> collided with this ADR's number. Read it from git history with
> `git show d97c1d8:docs/adr/0009-finding-b-verification.md`.

ADR 0004 defined the throughput bullwhip on "physical delivered flow from `SimulationState.transport_flows`"
and named the `collector -> treatment` link in that log as the Treatment echelon. The issue-09 sanity gate
comparing empirical results with theory, and the diagnosis that followed, showed that this premise is wrong
for the Treatment echelon. The `collector -> treatment` entries in `transport_flows` are not deliveries to
treatment at all. This ADR corrects the definition of the Treatment-echelon inbound flow. It supersedes ADR
0004's identification of that flow (and, through it, the Treatment-side numbers in ADRs 0006 and 0007). The
rest of ADR 0004 stays intact: CV² normalization, the consumption-`attempted` anchor, two echelons instead
of three, warm-up, and per-node-then-weighted aggregation.

## The defect (what the sanity gate caught)

There are only two `track_transport_flow` call sites. `core/transport_manager.py::_create_transport` logs
the `collector -> treatment` one. Only `collector.transfer_waste_to_region` feeds it, and only
`treatment._request_via_transport` calls that, for the cross-region portion of replenishment. Tracing it:

- `transfer_waste_to_region` removes the volume from the **remote** collector's collection center.
- On arrival, `_handle_completed_transport` puts that volume back into the **destination-region
  collector's** collection center. It never goes into a treatment operator.

So the logged `collector -> treatment` series is net-zero collector-to-collector **repositioning**, not
treatment intake. Treatment's real replenishment is `collector.provide_waste_for_treatment`, the local and
fallback intake that decrements collector storage directly and feeds the treatment process. It is never
logged to `transport_flows`. A monkey-patch ledger over weeks 0-52, seed 123456, confirmed this for every
PUSH and PULL combo. The logged series equals the volume transferred out, which equals the volume put back,
with zero net and zero drops, while the real intake is 5.2x-9.1x larger and missing from the log. Full
record: `docs/adr/0009-finding-b-verification.md`.

## Decision

1. **The Treatment-echelon inbound flow is `provide_waste_for_treatment` intake.** A `collector -> treatment`
   `track_transport_flow` is emitted where waste passes from a collector's collection center to a treatment
   operator. This is the delivered replenishment flow the bullwhip's Treatment echelon must read. It covers
   all intake: local, fallback, and the later local pickup of waste that arrived by cross-region
   repositioning.

2. **The cross-region transport is relabeled `collector -> collector`.** It is real physical movement
   between two collectors' collection centers in different regions, so it stays in `transport_flows` under a
   `collector -> collector` source/target pair instead of being dropped. It is a repositioning move inside
   the Collector echelon, not an ordering echelon, so no bullwhip echelon reads it.

3. **The flow graph therefore has three links:** `generator -> collector` (collection, the Collector
   echelon, unchanged), `collector -> collector` (repositioning, no echelon), and `collector -> treatment`
   (intake, the Treatment echelon, now correct).

4. **The MFA Sankey keeps the repositioning arc** under its new `collector -> collector` label, so the
   visualization still accounts for all mass. Transport cost and emissions accounting is computed
   separately, and the relabel does not affect it.

## No double-counting

> Partially superseded by ADR 0010. This section is correct for the flow *log*, but the code also credited
> the repositioned volume to treatment *storage* at request time, double-counting it in the physical stock.
> ADR 0010 fixed this, and the claim below holds only after that fix.

The repositioned volume is removed from one collector's storage and added to another's (net zero across the
Collector echelon). It counts as Treatment inbound only when `provide_waste_for_treatment` later draws it.
The three links are disjoint source/target pairs, so a unit of waste is counted at most once per echelon:
once as `generator -> collector` when collected, optionally once as `collector -> collector` if
repositioned, and once as `collector -> treatment` when it enters treatment.

## What this invalidates (pending re-run)

The previously published numbers that read the old `collector -> treatment` series measured repositioning,
not intake. They must be regenerated on the corrected flow (issue 12, which fulfils the issue-09 gate):

- `treatment_anchored` (its numerator was repositioning)
- `treatment_stage` (its numerator was repositioning)
- `collector_stage` (its **denominator** was repositioning, which caused the spurious `collector_stage < 1`
  reading)
- `treatment_anchored_pooled` (equals `treatment_stage` by construction)

These are unaffected because they never read the `collector -> treatment` series: the Collector echelon
(`collector_anchored` and `collector_anchored_pooled`, both on `generator -> collector` vs consumption) and
the source-variance floor (ADR 0005, on potential generation).

The structure of the stage decomposition (ADRs 0006, 0007) survives. `treatment_stage * collector_stage`
still telescopes to the clean pooled Collector anchored ratio, because the repositioning term cancels. But
each individual stage factor was meaningless as published, so the reading of "which echelon injects
amplification" is invalid until re-run. Expect the corrected Treatment echelon to read a much larger, less
lumpy flow (continuous real intake instead of sparse repositioning spikes), which may change whether
PUSH > PULL holds at that echelon. That re-evaluation is issue 09's verdict on the issue-12 dataset, not
part of this ADR.

## References

- `docs/adr/0009-finding-b-verification.md`: the static audit, runtime ledger sweep and impact map.
- Supersedes the Treatment-echelon flow identification in ADR 0004 and refines the Treatment-side numbers in
  ADRs 0006 and 0007. ADR 0005 (source floor) and the Collector echelon are unaffected.
