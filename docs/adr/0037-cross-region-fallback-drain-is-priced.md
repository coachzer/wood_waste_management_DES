# The cross-region fallback drain is priced

Date: 2026-11-18
Status: accepted

## Context

`TreatmentOperator._collect_with_fallback` drains any region's collector straight into treatment
through `provide_waste_for_treatment`. That drain carried about 72% of PULL intake and 26-42% of
PUSH intake on seed 1, with no transport cost or emissions. Routing it through the priced transfers
of ADR 0034 failed: PULL service fell about 48 points (see ADR 0034 and
`.scratch/recommended/ISSUE-routing-fallback-blocked.md`). A correct routing needs inventory position
and reserved transfers, which is a redesign. The user chose to price the drain as it stands.

## Decision

In `_drain_collectors`, a drain from a collector in another region is charged as one loaded trip
over `get_distance(collector region, operator region)`, through
`CollectorCompany._record_trip_cost_and_emissions` (the same rule as collection and transfers).
The draining collector pays. A drain within the operator's region is not charged, as before.

The drain still takes no travel time and uses no vehicle. That is the remaining approximation.

## Consequences

Seeds 1-10, Baseline, after minus before (paired, 95% CI), against ADR 0036. Every flow KPI
(service, collection rate, uncollected, outlet) is identical; only cost and emissions move.

| Combo | Collection transport cost, M | Emissions, t CO2e |
|---|---|---|
| PUSH ON_DEMAND | +0.79 | +125 |
| PUSH REORDER_50 | +0.52 | +111 |
| PUSH REORDER_90 | +0.59 | +112 |
| PULL ON_DEMAND | +1.25 | +266 |
| PULL REORDER_50 | +1.05 | +243 |
| PULL REORDER_90 | +1.13 | +248 |

PULL minus PUSH flips sign. Before, PULL was 0.34-0.38M cheaper and emitted 90-116 t less. Now:

| Strategy | Total cost, M | Emissions, t CO2e |
|---|---|---|
| ON_DEMAND | +0.11 [+0.07, +0.15] | +24 [+15, +33] |
| REORDER_50 | +0.15 [+0.10, +0.20] | +41 [+33, +50] |
| REORDER_90 | +0.19 [+0.16, +0.22] | +43 [+37, +48] |

PULL's earlier advantage came from moving most of its feedstock across regions for free.
Distances are great-circle, so both policies' transport is still understated by about 30%.
