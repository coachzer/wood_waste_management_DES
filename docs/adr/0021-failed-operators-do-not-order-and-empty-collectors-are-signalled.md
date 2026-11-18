# FAILED operators do not order waste, and treatment signals reach empty collectors in full

Date: 2026-11-18
Status: accepted

## Context

A review of the PUSH and PULL implementations (20 Baseline seeds, CRN, 95% paired-t intervals, no
multiplicity correction, instrumented runs that were fidelity-checked against uninstrumented ones)
found two defects in `TreatmentOperator` that were not part of the policy design:

1. `schedule_collection_requests` never checked `self.status`. A FAILED operator produces nothing
   but kept polling collectors and filling `waste_storage`. In the 20-seed runs it stored about
   2.57M m3 of waste across the 60 PULL runs (a similar amount across the 60 PUSH runs) while FAILED.
2. `_propagate_signal_to_collectors` signalled only local collectors that held the requested waste
   type, and capped the volume at their stock. Under PULL ON_DEMAND about 90% of treatment signals
   found no recipient, so the downstream pull signal was mostly absent. An empty collector is the one
   that has to pass the demand on to generators.

## Decision

- A FAILED operator's reorder loop waits one `OPERATING_TICK_DAYS` and re-checks. It neither produces
  nor orders.
- Treatment signals go to every available local PULL collector, whatever its stock of that waste type,
  and carry the full needed volume. This changes the volume rule from `min(need, stock)` to `need`,
  which is a separate behaviour change from reaching empty collectors.

Commits `68275bc` and `6ecdd61`. Four tests in `tests/core/test_treatment_outage_and_empty_collector.py`
fail on the old code and pass on the new.

## Consequences

Paired over 20 seeds, PULL after minus PULL before (95% interval):

| Strategy | Full service, points | Landfill, m3/year | Treatment bullwhip | Collector bullwhip |
|---|---|---|---|---|
| ON_DEMAND | +14.7 [+13.4, +16.1] | +8,810 [+6,511, +11,109] | +30 [+4, +56] | +33 [+21, +45] |
| REORDER_50 | +2.9 [+2.0, +3.8] | +6,414 [+3,098, +9,729] | -52 [-103, -2] | +7 [-2, +16] |
| REORDER_90 | +3.6 [+2.6, +4.7] | +18,437 [+13,821, +23,053] | -272 [-309, -234] | +16 [+4, +27] |

- **PULL service improves, and PULL landfill gets worse.** More waste now reaches collectors that are
  already full. The PULL-minus-PUSH landfill gap widens. PUSH has no landfill in these runs. This is an
  open problem, not an accepted trade-off. The likely cause is that collectors deposit concurrent
  dispatches and cross-region arrivals without a capacity check (one-seed evidence, not yet confirmed
  over seeds). ADR 0022 found the cause: PULL signals forced collection into full centers.
  Capacity checks on arrivals did not help.
- **PUSH changes too**, because the FAILED fix applies to both policies. The change in PUSH full service
  is within noise (ON_DEMAND +0.52 [-0.40, +1.43], REORDER_50 -0.12 [-0.31, +0.07], REORDER_90 +0.23
  [-0.15, +0.61]). Any comparison must pair PUSH and PULL from the same code version.
- **ADR 0020's stage-1 numbers describe the old code** and are not a regression oracle for this one.
- **The earlier belief that bullwhip runs higher under PULL was wrong** in the pre-fix 20-seed data.
  Collector bullwhip is lower under PULL in all three strategies. Treatment bullwhip is lower for
  ON_DEMAND, not significant for REORDER_50, and higher only for REORDER_90.
- Bullwhip magnitudes are inflated about 48x because weekly demand is nearly deterministic
  (CV2 of consumption about 0.021). Only between-policy comparisons are meaningful.

## Still open, not changed here

- ON_DEMAND is not lot-for-lot: S is about 174 weeks of demand, against CONTEXT.md's description.
- PULL and PUSH differ in collector thresholds and efficiency curves, so the comparison is confounded
  beyond information flow. The PULL efficiency bonus counts the whole shared signal bus.
- Generator signals carry no `target_region`, so other regions' collectors drop 21-66% of them.
  Fixed by ADR 0023, which stops collectors deleting signals they cannot serve.
- The PULL production backlog absorbs `attempted` with no expiry or cap.
- Signal expiry uses `<=` with a 1-day maximum age. Treatment signals are first seen at exactly age 1.0.
