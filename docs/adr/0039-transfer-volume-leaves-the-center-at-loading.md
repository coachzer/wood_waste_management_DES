# Transfer volume leaves the sending center when a vehicle loads it

Date: 2026-11-18
Status: accepted

## Context

`CollectorCompany.transfer_waste_to_region` debited the sending collection center when it queued
a `TransportRequest`, not when a vehicle took it. `request_transport` always returned True, so
every request was debited at once. Queued volume then sat in `PointToPointTransport.pending_requests`.
The mass-balance checks counted it as in transit, but no KPI or MFA node read it. Seed 1 PUSH
ON_DEMAND ended with 9,836 m3 queued, 9,836 of the 9,967 m3 MFA collector gap (the rest
was on vehicles still on the road). Meanwhile the debited volume
was invisible to everyone else: the fallback drain and local treatment could not take it, yet
the transfer still shipped the full amount when a vehicle came.

## Decision

`PointToPointTransport.process_requests` debits the origin center when it assigns a vehicle. It
loads `min(requested, stock still at the origin)`. A request whose stock is gone is dropped. Until
then the volume stays in the origin's `current_storage`, where every ledger already looks.
`SimulationState.pending_reposition_volume_by_origin` and its two uses in the mass-balance checks
are removed: queued volume is now ordinary center stock, and counting it again would double it.

Because queued volume stays in storage, a later cross-region request could claim it again and
count it against the order, though only one vehicle can load it (seed 1 PUSH ON_DEMAND: 3,476 m3
claimed twice). `_get_available_waste_from_collector` therefore subtracts
`PointToPointTransport.queued_volume` for that collector and waste type. Local intake and the
fallback drain may still take queued stock; the request then loads what remains.

## Consequences

Seeds 1-10, Baseline, paired against ADR 0038 (`.scratch/agy-review/loaddebit_effect.txt`).
Service is unchanged (PULL ON_DEMAND +0.00 [-0.00, +0.01]). Collection rate moves less than 0.1
points.

| Combo | Total cost, M | Transport cost, M | Emissions, t CO2e |
|---|---|---|---|
| PUSH ON_DEMAND | -0.10 [-0.13, -0.08] | -0.11 | -32 |
| PUSH REORDER_50 | -0.04 [-0.06, -0.02] | -0.04 | -6 |
| PUSH REORDER_90 | -0.06 [-0.08, -0.04] | -0.05 | -10 |
| PULL ON_DEMAND | -0.17 [-0.20, -0.14] | -0.11 | -51 |
| PULL REORDER_50 | -0.18 [-0.21, -0.14] | -0.18 | -39 |
| PULL REORDER_90 | -0.19 [-0.21, -0.18] | -0.18 | -44 |

Seed 1 ON_DEMAND: PULL transfers fall from 7,298 to 6,034 and 19.9k to 14.3k m3, because a
request whose stock was drained before a vehicle came is now trimmed or dropped. PUSH transfers
are almost unchanged (10,852 to 10,850). Its end-of-run queue falls from 9,836 to 2,230 m3, now
held as center stock.

PULL treatment-anchored bullwhip ON_DEMAND falls 0.40 [0.22, 0.58]. Collector-anchored bullwhip
falls 0.7-2.9 in five of six combos.

With the reservation (seeds 1-10, `.scratch/agy-review/reserve_effect.txt`) PUSH ON_DEMAND
total cost moves a further -0.02M [-0.04, -0.00]; nothing else moves beyond noise.

PULL minus PUSH narrows. Total cost: +0.06 [+0.04, +0.08] / +0.05 [+0.01, +0.09] /
+0.10 [+0.07, +0.13] M. Emissions: +14 / +24 / +23 t (ON_DEMAND / REORDER_50 / REORDER_90).
PULL is still dearer and dirtier than PUSH in every strategy, but the margin is small. The
round-1 agy review found two trip-pricing artefacts: one fixed trip cost per waste type per drain or
transfer, and a fallback drain that visits collectors in region enum order instead of nearest first.
Re-pricing seeds 1-10 under alternative rules (`.scratch/agy-review/robustness/summary.txt`) keeps
PULL dearer under every rule that treats drains and transfers alike (+0.03 to +0.17M; REORDER_50 not
significant under two rules). Only dropping the fee on drains while keeping it on transfers flips
the sign. Emissions stay higher for PULL under every rule.

The MFA "Stock at day 365" sink now includes the queued volume as collector stock, so the PUSH
collector node should close up to vehicles still on the road. Not re-checked here.

## Correction 2026-11-19: the robustness range was misread

The paragraph above misreads its own source. In `.scratch/agy-review/robustness/summary.txt`
(seeds 1-10, d91732b), PULL minus PUSH total cost under the rules that price drains and transfers
alike is:

| Fallback order | Rule | ON_DEMAND | REORDER_50 | REORDER_90 |
|---|---|---|---|---|
| Region order (current code) | As run | +0.06 [+0.04, +0.08] | +0.05 [+0.01, +0.10] | +0.10 [+0.07, +0.13] |
| Region order (current code) | One fee per trip, both kinds | +0.13 [+0.11, +0.16] | +0.03 [-0.01, +0.07] | +0.10 [+0.07, +0.13] |
| Region order (current code) | No fee on drains or transfers | +0.20 [+0.18, +0.22] | -0.01 [-0.05, +0.03] | +0.08 [+0.05, +0.11] |
| Nearest first | As run | +0.06 [+0.02, +0.09] | +0.13 [+0.09, +0.17] | +0.13 [+0.11, +0.14] |
| Nearest first | One fee per trip, both kinds | +0.17 [+0.14, +0.20] | +0.13 [+0.09, +0.17] | +0.15 [+0.13, +0.16] |
| Nearest first | No fee on drains or transfers | +0.22 [+0.19, +0.25] | +0.07 [+0.03, +0.11] | +0.11 [+0.10, +0.13] |

With the current region-order fallback, REORDER_50 has a negative point estimate when neither kind
pays a fee, and ON_DEMAND reaches +0.20M. The range is -0.01 to +0.20M, not +0.03 to +0.17M.
PULL is dearer under every symmetric rule only with a nearest-first fallback. Emissions stay higher
for PULL under all of them.

The "one fee per trip" rows are biased against PUSH. The probe groups transfers by the vehicle's
owner instead of by origin and destination, so it leaves some PUSH transfer fees unbatched. Per the
agy round-2 review, that is about 0.14M on seed 1 ON_DEMAND (not rerun here). Those rows understate
PULL minus PUSH.

The same review found that the reservation can go stale. `queued_volume` sums each request's
volume as queued. If local or fallback intake drains the sending center before a vehicle loads,
the reservation can exceed the stock and hold back stock that arrives later. On seed 1 PUSH
ON_DEMAND this happens on 766 ticks, about 2,084 m3 (agy's count, not rerun here). Loading still
clips to stock, so nothing is over-shipped.
