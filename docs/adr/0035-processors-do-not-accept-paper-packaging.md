# Processors do not accept paper packaging (15 01 01)

Date: 2026-11-18
Status: accepted

## Context

a35c483 added 15 01 01 (paper and cardboard packaging) and 20 01 38 to every processor's
`input_types`. 15 01 01 is paper, not wood. SURS sends 78% of it to recycling, which means paper mills,
not the MDF, particle board and OSB lines modelled here. Board mills take wood, not paper.

## Decision

15 01 01 is removed from every processor's `input_types` in all 12 region files. 20 01 38 stays.
Generators still produce 15 01 01 at its SURS rate.

## Consequences

Seeds 1-10, Baseline, after minus before (paired, 95% CI), against ADR 0034:

| Combo | Service, pts | Uncollected, m3 | Processing cost, M | Total cost, M |
|---|---|---|---|---|
| PUSH ON_DEMAND | 0.00 | +2.8k [-20.7k, +26.4k] | -0.93 | -0.94 [-1.02, -0.87] |
| PUSH REORDER_50 | 0.00 | 0 | | -0.94 [-0.97, -0.90] |
| PUSH REORDER_90 | 0.00 | 0 | | -0.98 [-1.01, -0.96] |
| PULL ON_DEMAND | +0.06 [-0.02, +0.15] | -10.5k [-11.2k, -9.9k] | -0.86 | -0.86 [-0.89, -0.83] |
| PULL REORDER_50 | 0.00 | -14.4k [-15.3k, -13.6k] | | -0.83 [-0.86, -0.80] |
| PULL REORDER_90 | 0.00 | -15.0k [-15.9k, -14.2k] | | -0.89 [-0.92, -0.87] |

- Service is unchanged: demand is met from the wood codes. The ADR 0031-0033 results were measured
  with 15 01 01 accepted. Service does not depend on it, but their cost and uncollected figures did.
- Processed volume falls 1-2% (1.5k-2.7k m3), but processing cost falls about 5%. The cause is the
  feedstock mix, not a shift between operators. Processing cost includes energy, charged per m3 at
  the transformation's `energy_required`. Without 15 01 01, intake moves to sawdust 03 01 05
  (energy 0.50) and away from wooden packaging 15 01 03 (0.95). Seed 1 PUSH ON_DEMAND: 03 01 05
  26.0k to 44.6k m3, 15 01 03 26.1k to 15.3k m3. Energy cost falls 0.79M and operational cost
  0.21M, against 0.93M observed. Per-operator volumes fall evenly (2-4%). Why intake reallocates
  to sawdust rather than pro rata was not traced.
- Collection rate falls 0.15-0.8 points. Treatment-anchored bullwhip moves by less than 0.5.
- 15 01 01 is now generated but no processor accepts it. ADR 0036 handles such codes.
