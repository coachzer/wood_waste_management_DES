# Treatment order-up-to level is sized from demand

Date: 2026-11-18
Status: accepted

## Context

Treatment ordered up to its waste storage capacity (ADR 0002). Capacity is 1,100 to 1,340 days of
throughput, so S was about three years of stock, and the REORDER_50 and REORDER_90 reorder points
sat at 1.5 and 2.7 years. In the textbook (s, S) and base-stock rules, S covers demand over the
protection period plus safety stock. It is not a physical limit.

## Decision

    S = D * n + z * sigma * sqrt(n),  clamped at waste storage capacity

- `D` is the waste needed per consumption interval (7 days): the operator's market share of
  producible annual demand / 52, divided by the blended conversion efficiency. It comes from
  parameters, not from a run, so PUSH and PULL get the same S. On seed 1 the parameter value is
  within 8% of measured consumption.
- `n` is the number of consumption intervals in the protection period (lead time + review
  period), at least 1. The lead time is 0, because `trigger_collection` drains collectors within
  the tick and no other path adds to treatment storage. The review period is the daily tick.
  Demand arrives in weekly lumps, so the protection period is one whole interval.
- `sigma = D * 0.141`, the standard deviation of the quarterly seasonal factor (amplitude 0.2).
  Market demand has no other variation.
- `z = 1.645` (95% cycle service level), confirmed by the user.

S is 127 to 565 m3 per operator, 0.71% of storage capacity. Each waste type's level is its share
of S (ADR 0026). The strategy reorder point is a fraction of that level, so the three strategies
still trigger at different stock levels.

ON_DEMAND is lot-for-lot: `s = S`, and the order is the gap, which is what was consumed.

Inventory position is on-hand stock (lead time 0), so ADR 0019 stands for treatment, with a note.

## Consequences

Mean over seeds 1-10, Baseline, and paired change against ADR 0026:

| Combo | Service level, % | Collection rate, % | Total system cost, EUR |
|---|---|---|---|
| PUSH ON_DEMAND | 100.0 (+11.6) | 16.2 (-5.9) | 19.1 M (+1.8 M) |
| PUSH REORDER_50 | 100.0 (+0.4) | 18.7 (-5.5) | 19.7 M (-0.6 M) |
| PUSH REORDER_90 | 100.0 (+1.6) | 23.6 (-7.6) | 20.2 M (-0.8 M) |
| PULL ON_DEMAND | 89.3 (-0.4, CI includes 0) | 14.2 (-9.8) | 16.3 M (-1.9 M) |
| PULL REORDER_50 | 99.6 (+0.5) | 22.0 (-7.3) | 20.4 M (-0.2 M) |
| PULL REORDER_90 | 97.3 (-0.2, CI includes 0) | 21.3 (-9.6) | 20.0 M (-0.5 M) |

- Treatment no longer stockpiles years of waste, so collection falls toward what treatment
  converts. Uncollected waste rises by 0.20 to 0.38 million m3 per combo, to 52-61% of potential
  generation. Landfill stays 0.
- The ON_DEMAND hoarding from ADR 0026 is gone under PUSH.
- Treatment-anchored bullwhip falls to about 1-3 in every combo, from 320-630. The collector
  stage ratio rises sharply (by 5 to 130). Not interpreted here; step 4 re-checks the bullwhip
  verdict.

Open defect: PULL ON_DEMAND is still about 11 points short, mostly OSB (20-46% short at every
operator on seed 1). A PULL signal for one waste type collects whatever streams the generator
holds, in dict order, so collection centers fill with 03 01 05 and reach the utilization ceiling.
At pomurska, 1 of 259 signals for 15 01 03 was served. PUSH does not have this path. The fix is a
separate commit.
