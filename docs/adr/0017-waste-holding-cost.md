# 0017 — Waste-side inventory holding cost at all three echelons

Date: 2026-06-11
Status: accepted

## Context

Cleanup #10 (`9b238a7`) removed the generator cost series (`energy_costs` /
`operational_costs` / `total_costs` in `generation_history`) because
`update_entity_costs` was never called for generators — every entry was a
permanent 0.0 stub and the readers summed guaranteed zeros. That left
`total_system_cost` with three components (collection/transport, processing,
storage overflow) and **no inventory-holding component at any echelon**:
waste could sit in storage indefinitely at zero cost. This is both
unrealistic and analytically flat — PUSH and PULL hold materially different
upstream inventory, so a missing holding cost suppresses a cost differential
between the very configurations the study compares.

The user ruled (2026-06-11): reintroduce generator cost properly as a
**holding cost**, applied at **all three echelons** (not generators only) to
avoid an asymmetric cost model.

## Decision

- New constant `WASTE_HOLDING_COST_PER_M3_PER_DAY = 0.005` ($/m³ per day,
  ~$1.83/m³-year) in `config/constants.py`. **Uncalibrated placeholder** in
  the same class as `CARBON_PRICE_EUR_PER_KG_CO2E`: flag for the paper before
  any cost number leans on it, and restate with the currency-consistency work
  (`.scratch/currency-consistency/`).
- Accrual point is the daily monitor sample (`monitor_system_process` yields
  `timeout(1)`): each `track_generation` / `track_collection` /
  `track_processing` call appends `stored m³ × rate` to a per-entity
  `holding_costs` series — one sample is exactly one day of holding cost.
  Treatment's accrual sits inside the existing same-timestamp guard, so the
  operator-loop re-entry of `track_processing` cannot double-accrue.
- The cost base is **waste-side storage only**: `generator.current_storage`,
  the collector's collection-center storage, and `treatment.current_storage`.
  Finished-goods inventory is deliberately excluded — finished panels are a
  different commodity with a different (higher) holding rate; pricing them at
  the waste rate would be false precision. Named as future work.
- `holding_costs` is a **separate series** from `total_costs` /
  `operational.total_costs`, so the existing `collection_transport_cost` and
  `processing_cost` KPI components stay pure. The KPI layer sums all three
  echelons into a new `holding_cost` KPI and `total_system_cost` becomes the
  sum of four components.
- Generators get back exactly one cost series (`holding_costs`); the cleanup
  #10 removal of the zero-stub trio stands.

## Consequences

- `total_system_cost` rises everywhere and is **no longer comparable to any
  pre-0017 cost figure**; the paper regenerates all numbers fresh anyway
  (freeze regime abandoned, 2026-06-09).
- The cost KPI now carries a policy-sensitive inventory term: configurations
  that park more waste upstream pay for it. Expect a PUSH/PULL cost
  differential component that did not exist before.
- The accrual is pure arithmetic on already-tracked state — no RNG, no new
  enum-set iteration — so CRN pairing and byte-determinism are unaffected
  (full suite incl. `test_determinism.py` green).
- The daily-sample accrual quantizes holding cost at 1-day resolution;
  intra-day storage swings are invisible to it. Consistent with every other
  monitor-sampled series.
