# Codes no processor accepts leave through an outlet

Date: 2026-11-18
Status: accepted

## Context

After ADR 0035, no processor in the country accepts 7 of the 14 generated codes (03 03 01, 03 03 08,
15 01 01, 19 12 01, 19 12 07, 20 01 01, 20 03 07). Their waste entered generator storage, filled
it, and was then counted as uncollected (ADR 0024). Under PUSH, collectors carried it to collection
centers, where it sat. SURS shows this waste going somewhere real, mostly to recycling outside the
board industry and to disposal. It does not vanish. The collection rate also used it in its
denominator, so the rate measured the processor input list, not collection.

## Decision

- `SimulationManager` builds the national accepted set: the union of every processor's
  `input_types`, sorted by EWC code. Each generator receives it.
- For any other code, the generator adds the period's potential volume to `total_outlet` and does
  not put it into storage. The draw that produces the volume is unchanged.
- Generator mass balance: `potential = committed + uncollected + outlet`.
- `collection_rate_pct` and `overall_efficiency_pct` divide by potential minus outlet.
  `collection_rate_all_generation_pct` keeps the old denominator for context.
- `outlet_volume_m3` and `outlet_by_destination` report the outlet. The second applies the 2022-2024
  SURS treatment shares per code from `data/outlet_destination_shares.json`, written by
  `data/calibrate_outlet_shares.py`. These shares are used only for reporting; the model does not
  route outlet waste and charges it no cost or emissions. That is an assumption.

## Consequences

Seeds 1-10, Baseline. Outlet is 664,631 m3 of 984,944 m3 potential (67.5%), identical under PUSH
and PULL in all 30 seed pairs. By SURS destination: recycling 359,835, disposal 177,947,
other recovery 125,774, energy recovery 1,074 m3.

After minus before (paired, 95% CI), against ADR 0035:

| Combo | Service, pts | Uncollected, m3 | Collection transport cost, M | Emissions, t CO2e |
|---|---|---|---|---|
| PUSH ON_DEMAND | 0.00 | -42.4k, to 0 | -0.51 | -241 |
| PUSH REORDER_50 | 0.00 | 0 | -0.66 | -327 |
| PUSH REORDER_90 | 0.00 | 0 | -0.99 | -432 |
| PULL ON_DEMAND | 0.00 | -216.4k, to 0 | -0.008 | -1.3 |
| PULL REORDER_50 | 0.00 | -218.8k, to 0 | -0.011 | -1.8 |
| PULL REORDER_90 | 0.00 | -216.9k, to 0 | -0.012 | -1.5 |

- Uncollected volume is now zero in every run. Accepted generation (about 320k m3/yr) fits in
  generator storage (1.0M m3). The uncollected KPI of ADRs 0024 and 0032 measured outlet codes
  filling storage. It no longer separates the policies.
- Collection rate on the accepted basis: PUSH 99.2-99.8%, PULL 39.4%. On all generation: PUSH 32%,
  PULL 12.8%, as before.
- PUSH no longer hauls outlet codes to collection centers, so its transport cost and emissions fall
  by about a third to a half. PULL barely moves, because it never ordered them.
- Total system cost falls 0.5-1.6M. On ON_DEMAND, holding cost falls 0.63M (PUSH) and 0.53M (PULL)
  because outlet codes no longer sit in storage, and PUSH transport falls 0.51M.
