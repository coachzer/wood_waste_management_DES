# Cross-region treatment intake was double-counted; the waste-side mass balance now enforces conservation

Date: 2026-06-04
Status: accepted

## Context

The system-wide waste-side mass-balance invariant (issue C3) defines raw-waste conservation:

    sum(generated) + initial_treatment_storage + initial_collection_center
        == generator_storage + in_transit + collection_center_storage
         + treatment_storage + treated_intake + landfilled

Building it exposed a real leak on the *clean* baseline. The right side exceeded the left by exactly
the cross-region (`inter_region_transport`) volume: 45,208.48 m3 on the Baseline / PUSH / ON_DEMAND
seed-123456 run. Three independent measures matched to the last decimal: the inter-region flow total,
treatment-received minus logged `treatment_intake` flows, and the raw RHS-LHS imbalance.

The trace: when a treatment operator pulls waste cross-region, `TreatmentOperator._collect_from_cross_region`
called `_request_via_transport`, which calls `CollectorCompany.transfer_waste_to_region`. That method
removes the waste from the *source* collector and dispatches a transport whose only effect is to put the
volume into the *destination* collector's collection center (`_handle_completed_transport`). It is a
collector-to-collector **repositioning** move, as ADR 0009 describes. But `_request_via_transport` *also*
returned that volume into the operator's `collected_waste`, which `trigger_collection` then passed to
`_add_to_storage`, crediting **treatment storage** with the same volume at request time. The same unit of
waste therefore sat in two stock buckets at once: in the destination collection center (in transit, then
on hand) and in treatment storage.

ADR 0009's "No double-counting" section stated that the repositioned volume is "only counted as Treatment
inbound when it is later drawn by `provide_waste_for_treatment`." That was correct for the *flow log* but
not for the *physical stock*. The code added the volume to treatment storage immediately, regardless of
any later local draw. The mass-balance invariant made the discrepancy visible.

## Decision

1. **Cross-region transport repositions waste and does not deliver it to treatment.**
   `_collect_from_cross_region` no longer adds the transported volume to `collected_waste`. Only real
   intake (`provide_waste_for_treatment`, local and fallback) credits treatment storage. The repositioned
   volume still covers the cross-region portion of the request (it is deducted from `remaining`, so the
   call does not fall through to fallback over-collection). It reaches treatment only when treatment later
   picks up locally from the destination collector's now-larger stock. This is the model ADR 0009 intended,
   and the storage credit was the bug.

2. **The waste-side mass balance is enforced.** `MassBalanceMonitor.check_waste_system` checks the identity
   above on the drained run (final only, like the per-collection-center check) and aborts on violation, as
   the product invariant does. Single runs raise. Batch Monte Carlo warns and continues.

## Consequences

This is a **behaviour change**, not additive analysis, and it is the one bucket-C slice that breaks the
freeze. Removing the phantom treatment feedstock lowers treatment throughput and service level, and it
exposes waste that had been absorbed without any record. Across the 10-rep Baseline candidate, total
generated rises about 4-5%, service level falls about 1-3 pp, and landfill volume and emissions rise about
30%. The golden additive gate therefore mismatches 60/60 against `baseline-2` *by design*.

**`baseline-2` is superseded and must be re-frozen** (as `baseline-3`) on the corrected flow before the
Phase 3 dataset and the paper use any numbers. Every published treatment, service-level, landfill or
emissions figure from before this fix measured the double-counted system and must be regenerated. The
bullwhip echelon series (ADR 0009) keep their *direction*, since they read flow logs, which were already
correct. Their magnitudes shift with the corrected throughput, so they are re-run with everything else.

The cross-process determinism guard stays green. The fix removes a storage credit and adds no unordered
set-of-enum iteration.
