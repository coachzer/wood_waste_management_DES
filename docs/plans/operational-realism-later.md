# Operational realism — later stages and follow-ups

Carried over from the stage-1 task list (ADR 0020, daily operating clock).

## Stages 2-4 (out of scope for stage 1)

- **Stage 2: capacity-loss failures.** Failures reduce capacity rather than only skipping
  ticks.
- **Stage 3: collector fleets.** Make vehicle count and size data, not 3 x one tick of
  collection. Related pre-existing behaviour, found in the stage-1 review:
  `collection_capacity` clamps each trip, not each tick (`collect_from_generator`), so a
  three-vehicle fleet can move up to 3x the per-tick capacity in one tick.
- **Stage 4: working-day calendar and continuous seasonality.** Replace the quarter-step
  Seasonal Pattern.

## Follow-ups found during stage 1

- **PULL backlog vs cadence confound.** A no-carry control run would separate "daily clock"
  from "shortfalls no longer forgotten" in the PULL gains (ADR 0020 a).
- **Transport distance mix.** Per-m³ transport emissions fell 7.5-17% under the daily clock,
  so average haul distance per m³ fell. The mechanism is not traced.
- **Fixed per-trip `transport_cost`.** It is charged on empty trips too. Daily trips raise its
  per-m³ share to $0.04-0.30/m³. Decide whether a fixed charge per trip is the intended cost
  model.
- **`TreatmentOperator.utilization_history`.** It is written but never read; remove it or use
  it.
- **Collector `max(10, ...)` capacity floor.** It never binds with the current data (minimum
  750 m³/day); remove it or justify it.
