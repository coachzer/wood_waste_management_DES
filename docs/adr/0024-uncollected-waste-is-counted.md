# Uncollected waste is counted

Date: 2026-11-18
Status: accepted

## Context

Generators cap generation at free storage (`WasteGenerator._generate_waste_for_period`). Waste
offered while storage is full was added to `total_potential_generated` and then dropped: no ledger
recorded it, and the waste-side mass balance starts from committed generation, so it could not see
the loss.

Measured on seed 1, Baseline, at e360967: 45 to 52% of potential generation (1.79 to 2.05 million m3
of 3.99 million) never entered the system, in all six policy and strategy combinations. Material flow
analysis requires every input to reach a counted fate. It also explains why landfill reads 0: the
overflow vanished before it could reach a landfill path.

## Decision

Waste generated while storage is full is **uncollected waste**. Each generator accumulates it per
waste type in `total_uncollected`. It is recorded in the generation history, reported as the
`uncollected_volume_m3` KPI, and checked by `MassBalanceMonitor.check_generators`:

    total_potential_generated == total_generated + total_uncollected

The two right-hand terms accumulate separately, so the check is not a subtraction.

Uncollected waste has no known destination, so it gets no landfill cost or emissions. This was the
implementer's default. The user was unsure whether it should count as landfill instead, so step 4
of the methodology work runs a landfill sensitivity case.

The storage cap itself is unchanged: waste types still fill free storage in dict order, so later
types can be starved. A proportional split would change waste composition and is left open.

## Consequences

- No existing result changes. All 60 reference runs (seeds 1-10, six combos) are byte-identical in
  every monitor key except the new `total_uncollected` series and the new KPI.
- A generation path that drops or invents waste now trips an armed run.
