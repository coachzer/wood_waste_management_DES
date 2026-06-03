# Treatment-echelon inbound flow is collector intake, not the cross-region transport log

ADR 0004 defined the throughput bullwhip on "physical delivered flow from `SimulationState.transport_flows`"
and named the Treatment echelon the `collector -> treatment` link in that log. The issue-09 empirical-vs-
theory sanity gate, and the diagnosis it triggered, showed that premise is wrong for the Treatment echelon:
the `collector -> treatment` entries in `transport_flows` are not deliveries to treatment at all. This ADR
corrects the definition of the Treatment-echelon inbound flow. It supersedes ADR 0004's identification of
that flow (and, transitively, the Treatment-side numbers in ADRs 0006 and 0007); it leaves the rest of ADR
0004 — CV² normalization, the consumption-`attempted` anchor, two-echelons-not-three, warm-up, per-node-
then-weighted aggregation — intact.

## The defect (what the sanity gate caught)

There are only two `track_transport_flow` call sites. The `collector -> treatment` one is logged by
`core/transport_manager.py::_create_transport`, fed only by `collector.transfer_waste_to_region`, called
only from `treatment._request_via_transport` for the cross-region portion of replenishment. Tracing it:

- `transfer_waste_to_region` removes the volume from the **remote** collector's collection center.
- On arrival, `_handle_completed_transport` re-deposits that volume into the **destination-region
  collector's** collection center — never into a treatment operator.

So the logged `collector -> treatment` series is net-zero collector-to-collector **repositioning**, not
treatment intake. Treatment's real replenishment is `collector.provide_waste_for_treatment` (the local and
fallback intake that decrements collector storage directly and feeds the treatment process), which is never
logged to `transport_flows`. A monkey-patch ledger over weeks 0-52, seed 123456, confirmed this across every
PUSH and PULL combo: the logged series equals transferred-out equals re-deposited with zero net and zero
drops, while the real intake is 5.2x-9.1x larger and invisible to the log. Full record:
`.scratch/bullwhip/FINDING-B-VERIFICATION.md`.

## Decision

1. **The Treatment-echelon inbound flow is `provide_waste_for_treatment` intake.** A `collector -> treatment`
   `track_transport_flow` is emitted at the point waste is handed from a collector's collection center into a
   treatment operator. This is the delivered replenishment flow the bullwhip's Treatment echelon must read.
   It captures all intake — local, fallback, and the eventual local pickup of waste that arrived by cross-
   region repositioning.

2. **The cross-region transport is relabeled `collector -> collector`.** It is genuine physical movement
   between two collectors' collection centers in different regions, so it stays in `transport_flows` under a
   `collector -> collector` source/target pair rather than being dropped. It is an intra-Collector-echelon
   repositioning move, not an ordering echelon, so no bullwhip echelon reads it.

3. **The flow graph therefore has three links:** `generator -> collector` (collection, the Collector
   echelon, unchanged), `collector -> collector` (repositioning, no echelon), and `collector -> treatment`
   (intake, the Treatment echelon, now correct).

4. **The MFA Sankey keeps the repositioning arc** under its new `collector -> collector` label, so the
   visualization stays mass-complete. Transport cost/emissions accounting is computed separately and is
   unaffected by the relabel.

## No double-counting

The repositioned volume is removed from one collector's storage and added to another's (net-zero across the
Collector echelon), and is only counted as Treatment inbound when it is later drawn by
`provide_waste_for_treatment`. The three links are disjoint source/target pairs, so a unit of waste is
counted at most once per echelon: once as `generator -> collector` when collected, optionally once as
`collector -> collector` if repositioned, and once as `collector -> treatment` when it enters treatment.

## What this invalidates (pending re-run)

The previously published numbers that read the old `collector -> treatment` series measured repositioning,
not intake, and must be regenerated on the corrected flow (issue 12, fulfilling the issue-09 gate):

- `treatment_anchored` (numerator was repositioning)
- `treatment_stage` (numerator was repositioning)
- `collector_stage` (its **denominator** was repositioning — the source of the spurious `collector_stage < 1`
  reading)
- `treatment_anchored_pooled` (equals `treatment_stage` by construction)

Unaffected, because they never read the `collector -> treatment` series: the Collector echelon
(`collector_anchored`, `collector_anchored_pooled` — both on `generator -> collector` vs consumption) and
the source-variance floor (ADR 0005, on potential generation).

The stage-decomposition story (ADRs 0006, 0007) survives structurally — `treatment_stage * collector_stage`
still telescopes to the (clean) pooled Collector anchored ratio, because the repositioning term cancels — but
each individual stage factor was meaningless as published, so the "which echelon injects amplification"
reading is invalid until re-run. Expect the corrected Treatment echelon to read a much larger, less lumpy
flow (continuous real intake rather than sparse repositioning spikes), which may change whether PUSH > PULL
holds at that echelon; that re-evaluation is issue 09's verdict on the issue-12 dataset, not this ADR.

## References

- `.scratch/bullwhip/FINDING-B-VERIFICATION.md` — the static audit, runtime ledger sweep, and impact map.
- Supersedes the Treatment-echelon flow identification in ADR 0004; refines the Treatment-side numbers in
  ADRs 0006 and 0007. ADR 0005 (source floor) and the Collector echelon are unaffected.
