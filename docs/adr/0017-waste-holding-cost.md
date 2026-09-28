# Waste-side inventory holding cost at all three echelons

Date: 2026-06-11
Status: accepted

## Context

Cleanup #10 (`9b238a7`) removed the generator cost series (`energy_costs` /
`operational_costs` / `total_costs` in `generation_history`), because nothing
ever called `update_entity_costs` for generators. Every entry was a permanent
0.0 stub, and the readers summed guaranteed zeros. That left
`total_system_cost` with three components (collection/transport, processing,
storage overflow) and **no inventory-holding component at any echelon**, so
waste could sit in storage indefinitely at zero cost. That is unrealistic, and
it also hides a difference the study cares about. PUSH and PULL hold very
different amounts of upstream inventory, so a missing holding cost suppresses
a cost difference between exactly the configurations the study compares.

The user ruled (2026-06-11) to bring generator cost back properly as a
**holding cost**, applied at **all three echelons** (not generators only) to
keep the cost model symmetric.

## Decision

- New constant `WASTE_HOLDING_COST_PER_M3_PER_DAY = 0.005` ($/m³ per day,
  about $1.83/m³-year) in `config/constants.py`. It is an **uncalibrated
  placeholder**, like `CARBON_PRICE_EUR_PER_KG_CO2E`. Flag it in the paper
  before any cost number depends on it, and restate it with the
  currency-consistency work (`.scratch/currency-consistency/`).
- Cost accrues at the daily monitor sample (`monitor_system_process` yields
  `timeout(1)`). Each `track_generation` / `track_collection` /
  `track_processing` call appends `stored m³ × rate` to a per-entity
  `holding_costs` series, so one sample is exactly one day of holding cost.
  Treatment's accrual sits inside the existing same-timestamp guard, so the
  operator loop calling `track_processing` again cannot accrue twice.
- The cost base is **waste-side storage only**: `generator.current_storage`,
  the collector's collection-center storage, and `treatment.current_storage`.
  Finished-goods inventory is excluded on purpose. Finished panels are a
  different commodity with a different (higher) holding rate, and pricing them
  at the waste rate would be false precision. This is named as future work.
- `holding_costs` is a **separate series** from `total_costs` /
  `operational.total_costs`, so the existing `collection_transport_cost` and
  `processing_cost` KPI components stay pure. The KPI layer sums all three
  echelons into a new `holding_cost` KPI, and `total_system_cost` becomes the
  sum of four components.
- Generators get back exactly one cost series (`holding_costs`). The cleanup
  #10 removal of the zero-stub trio stands.

## Consequences

- `total_system_cost` rises everywhere and is **no longer comparable to any
  cost figure from before 0017**. The paper regenerates all numbers fresh
  anyway (freeze regime abandoned, 2026-06-09).
- The cost KPI now includes a policy-sensitive inventory term. Configurations
  that park more waste upstream pay for it. Expect a PUSH/PULL cost difference
  that did not exist before.
- The accrual is pure arithmetic on state that is already tracked, with no RNG
  and no new enum-set iteration, so CRN pairing and byte-determinism are
  unaffected (full suite including `test_determinism.py` green).
- The daily-sample accrual measures holding cost at 1-day resolution and
  misses storage swings within a day. Every other monitor-sampled series works
  the same way.
