# Generation rates are calibrated to SURS

Date: 2026-11-18
Status: accepted

## Context

The generator rates in `data/regions/*.json` were partly calibrated to data and partly invented
to test the system. Nobody recorded which were which. Summed over the country they gave 1.85 Mt/yr
for the 14 model codes.

SURS ODP 2024 records 184 kt of business generation for the same codes, and 767 kt treated, which
is an upper bound because waste passing through R_12 and then R_03 is counted twice. None of the
134 region-code rates was within 5% of SURS 2024. 73 were more than twice SURS, and some codes
were more than 1,000 times too high (03 01 01, 03 03 01). The over-generation caused the 52-61%
uncollected overflow in ADR 0024.

## Decision

`data/calibrate_generation_rates.py` rebuilds every rate from the user's SURS pipeline
(`green-up-project`, filtered CSVs):

    rate (t/day) = mean over 2022-2024 of
                   (business generated_in_the_year + municipal total_waste_given_away) / 365

- Business generation is ODP-nastajanje. Municipal hand-over is ODP-zbiranje, so household waste
  collected by public services is included.
- A code SURS does not report for a region is left out of that region's generator, not filled in.
- The three-year mean keeps one odd year from setting the rate.

Total generation is now 0.44 Mt/yr (985,000 m3).

Capacities (generator storage, collector, treatment) and demand were not recalibrated. They may
also include invented values.

## Consequences

Mean over seeds 1-10, Baseline:

| Combo | Service, % | Collection, % | Uncollected, m3 | Cost, model currency M | Emissions, t CO2e |
|---|---|---|---|---|---|
| PUSH ON_DEMAND | 99.98 | 61.8 | 54,148 | 17.9 | 584 |
| PUSH REORDER_50 | 99.99 | 71.0 | 2,049 | 18.4 | 663 |
| PUSH REORDER_90 | 100.00 | 85.8 | 0 | 18.5 | 759 |
| PULL ON_DEMAND | 90.46 | 27.9 | 136,650 | 16.8 | 445 |
| PULL REORDER_50 | 92.76 | 40.0 | 47,761 | 17.4 | 541 |
| PULL REORDER_90 | 82.46 | 28.4 | 67,525 | 15.6 | 431 |

- Uncollected falls from 52-61% of generation to 0-14%. Generators are full on at most 6% of days,
  against 39-45% before. The overflow question from ADR 0024 mostly goes away. Landfill stays 0.
- Paired PULL minus PUSH service is now negative in every strategy. ON_DEMAND is -9.5 [-12.3, -6.7],
  REORDER_50 -7.2 [-7.8, -6.7] and REORDER_90 -17.5 [-18.3, -16.8]. Before calibration, the PULL
  REORDER strategies served 100%. PULL is cheaper and emits less only because it collects and
  sells less.
- The PULL shortfall sits in the western operators (gorenjska, goriska, obalno_kraska,
  primorskonotranjska), and MDF is hit hardest (21-27% served on seed 1, REORDER_90). Likely
  cause, from probes in `.scratch/agy-needs/` (seed 1-2, not yet in the model):
  - Little local feedstock. The processors don't accept 15 01 01 or 20 01 38, so the western
    regions generate only 0.04-4.4 t/day of MDF inputs they take, against 29 t/day in
    jugovzhodna_slovenija.
  - PULL treatment signals go only to the local collector, so a deficit region never asks a
    surplus region.
  - Each collector has 3 vehicles, and signals are served in code order, so tiny 02 01 07 and
    03 01 01 orders use them up first.
  Probe results:
  - With both signal fixes applied, PULL serves 100%.
  - Removing generator storage triggers under PULL without those fixes drops service to 64%
    (REORDER_90).
  Ruled out: waste stranded in another region's center, and the cross-region drain share. An
  earlier version of this ADR also ruled out missing local feedstock. That was wrong, because it
  counted codes the processors don't accept.
