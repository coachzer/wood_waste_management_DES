# Transport cost and emissions use road distance

Date: 2026-11-18
Status: accepted

## Context

The distance matrix is great-circle. ADR 0015 made `transportation_time` a road-circuity factor
for travel time only and left cost and emissions on the straight line, a known understatement
of about 30-40%. Every trip is charged in one place,
`CollectorCompany._record_trip_cost_and_emissions`: collection trips, inter-region transfers
(ADR 0034) and cross-region fallback drains (ADR 0037).

## Decision

`ROAD_CIRCUITY_FACTOR = 1.35` in `config/constants.py`. `_record_trip_cost_and_emissions`
multiplies the great-circle distance by it before charging per km per m3 and per ton-km.

- A constant, not the scenario's `transportation_time`. Stress scenarios stretch
  `transportation_time` to 4.0 to model slow transport; that must not quadruple fuel and cost.
- Deterministic, not the per-trip draw. No extra RNG draws, so CRN pairing and flows are untouched.
- 1.35 is the value ADR 0015 chose for the baseline time factor (inside its stated 30-40% band).
  Neither ADR cites a primary source for the band. A literature detour index for Slovenian
  roads would replace it.

## Consequences

Seeds 1-10, Baseline, paired against a072cef (`.scratch/agy-review/roadkm_effect.txt`). Every
flow KPI, service level and bullwhip value is identical. Only cost and emissions move:

| Combo | Transport cost, M | Emissions, t CO2e |
|---|---|---|
| PUSH ON_DEMAND | +0.35 | +110 |
| PUSH REORDER_50 | +0.30 | +96 |
| PUSH REORDER_90 | +0.31 | +97 |
| PULL ON_DEMAND | +0.36 | +119 |
| PULL REORDER_50 | +0.34 | +111 |
| PULL REORDER_90 | +0.34 | +112 |

PULL moves more volume between regions, so its gap over PUSH widens. PULL minus PUSH, total cost:
+0.12 [+0.07, +0.17] / +0.19 [+0.13, +0.24] / +0.23 [+0.19, +0.27] M; emissions +33 / +56 / +57 t
(ON_DEMAND / REORDER_50 / REORDER_90).

The pre-trip estimate in `_unified_collection_strategy` (`ESTIMATED_COLLECTION_COST_PER_KM`)
still uses great-circle km. Its caller discards the return value, so no KPI reads it.
