# 0020 — Treatment and collectors run on a daily operating clock at unchanged annual capacity

Date: 2026-09-28
Status: accepted

## Context

Before this change each active entity looped on the period the region data sizes its capacity in:

- **Treatment** woke every `processing_time` days (24 in every region JSON) and ran
  `waste_storage_capacity * PROCESSING_CAPACITY_FRACTION` per transformation per wake-up.
  Its reorder poll (`schedule_collection_requests`) ran on the same 24-day loop.
- **Collectors** woke every `collection_frequency` days (12 in every region JSON) plus a
  `uniform(1, 4)`-day jitter (`collection_timeout`). PULL skipped the jitter only when kanban
  signals were pending. Each wake-up could move up to `collection_capacity` per trip.

Market consumption is weekly (`CONSUMPTION_INTERVAL_DAYS = 7`), failures already roll daily
(commit b96b320), and the monitor samples daily. So a PULL operator heard about demand
weekly but could act on it only every 24 days, and collectors acted every 12-16 days. This is
stage 1 of the operational-realism rework. It moves treatment and collectors onto a 1-day
clock without changing any entity's annual capacity, so its effect on the results can be
measured on its own.

## Decision

`OPERATING_TICK_DAYS = 1.0` (`config/constants.py`). Treatment's production loop, treatment's
reorder poll, and the collector loop (including its FAILED skip) all yield
`OPERATING_TICK_DAYS`. Per-tick capacity comes from one helper:

```python
# utils/capacity_utils.py
def per_tick_capacity(capacity_per_period, period_days):
    return capacity_per_period * OPERATING_TICK_DAYS / period_days
```

So `per_tick * 365 / OPERATING_TICK_DAYS == capacity_per_period * 365 / period_days` for any
tick length. The region JSONs are unchanged. `processing_time` and `collection_frequency` now
mean "the period the capacity figure refers to", not the loop cadence. The rescaling lives in
the entity constructors, so every construction path (builder or direct, including tests) gets
it.

### Annual capacity is preserved in every state

- **Treatment**: `processing_capacity = per_tick_capacity(storage * 0.8, processing_time)` is
  set once at construction and kept as `initial_processing_capacity`.
- **Storage expansion**: an `EXPANSION_SIZE_M3 = 500` expansion raises
  `waste_storage_capacity` only. Processing capacity never followed expansions, before or
  after this change, so it stays unchanged here too.
- **RECOVERING ramp**: `_apply_status_throughput_effects` scales `initial_processing_capacity`
  (now per-day) by `get_operational_efficiency()`. The ramp therefore runs at the same fraction
  of the same annual rate. The ramp is time-based (days since recovery started), not
  tick-based, so its length is unchanged.
- **Collector**: `initial_collection_capacity = per_tick_capacity(collection_capacity,
  collection_frequency)`. The efficiency scaling (`collection_capacity = max(10, initial *
  efficiency)`) applies to that per-day value. The `max(10, ...)` floor never binds with the
  current data. The smallest per-day value is 30,000 / 12 * 0.3 = 750 m³: the smallest
  region `collection_capacity` at the 0.3 efficiency clamp in `update_efficiency`. FAILED
  ticks are skipped before the recompute.
- **Collection-center storage** stays `2 * collection_capacity` at the data-period value. It
  is a stock, not a flow, and shrinking it 12× would turn the change into a storage cut.

No KPI definition changed.

### Couplings

**a. PULL production backlog: carry unmet targets forward.** Before this change, a PULL
operator set each product's target to that tick's Consumption Event `attempted`. It produced
what capacity and waste allowed and dropped the rest. On a daily clock, one day's capacity is
1/24 of the old per-tick capacity, so a weekly Consumption Event can no longer be produced in
one tick, and dropping the shortfall would silently cut PULL output about 7×. The operator now
keeps `pull_production_backlog[product]`:

- `_absorb_market_signals` reads this operator's unacknowledged Market Signals. For each, it
  adds the `attempted` of the matching Consumption Events (same operator and timestamp,
  `reason != "no_capability"`) to the backlog, then acknowledges the signal.
- `_produce_for_backlog` produces each product with `output_cap = backlog` and subtracts what
  it made. The finished-goods headroom clamp still applies, which bounds the backlog's
  physical effect.
- Absorption runs **before** the FAILED check. Otherwise demand that arrives during an outage
  longer than the signal max age (coupling b) would be pruned unseen.
- There is no expiry.
- `no_capability` events are skipped because the operator cannot produce them.

The backlog is internal production state only. It never writes a Consumption Event, never
changes `attempted` or `consumed`, and plays no part in Lost Sales or Service Level. Those are
still computed at the market from the consumption-event log, so a Lost Sale stays lost even
when the backlog later produces the volume (that product lands in finished goods for later
ticks). Term added to CONTEXT.md: **PULL Production Backlog**.

Known confound: the old loop also dropped targets it missed for lack of waste. The backlog
keeps those too. PULL's change in results therefore mixes "daily cadence" with "no longer
forgets shortfalls". The two cannot be separated without a no-carry control run, which is not
done here.

**b. `KANBAN_SIGNAL_MAX_AGE_DAYS = OPERATING_TICK_DAYS` (was 24.0).** Derived from the slowest
signal consumer rather than shrunk proportionally:

- The old 24.0 equalled treatment's 24-day tick, the slowest reader of the bus, so a signal
  lived exactly one read cycle of its slowest consumer.
- Every consumer (treatment, collectors, generators) now reads the bus once per
  `OPERATING_TICK_DAYS`, so one read cycle is 1 day.
- Level-based signals (treatment reorder gaps, generator stock) are re-raised every tick while
  the condition holds. Older copies would only let a collector act on a superseded gap.
- Market Signals are the one edge-triggered kind. A FAILED PULL operator still absorbs them
  (coupling a), so a 1-day life loses none.
- All ticks fall on integer times and the prune keeps `age <= max_age`, so a signal raised on
  day t is visible to every day-t and day-t+1 reader.

**c. PUSH collector jitter: removed.** Adding `uniform(1, 4)` to a 1-day tick would make the
effective cadence 3.5 days. Scaling the jitter to the tick (`uniform(1/12, 4/12)`) would keep
randomness but make the mean cadence about 1.2 days, not daily. The spec asks for a daily
effective mean, so the jitter is dropped, along with `collection_timeout` in the
`InventoryPolicy` protocol and its three tests. **Side effect on effective capacity:** the old
PUSH cadence averaged 12 + 2.5 = 14.5 days against capacity sized per 12 days, so PUSH
collectors delivered about 12 / 14.5 ≈ 83% of nominal annual capacity. PULL delivered between
83% and 100%, depending on how often signals were pending. Both now deliver 100% of nominal.
Collector effective capacity therefore rises about 20% for PUSH. That is a real change in
effective capacity, even though nominal capacity is preserved.

**d. Vehicle capacity: set explicitly to one tick of collection.** `FacilityBuilder.
create_collector` passes `vehicle_capacity = per_tick_capacity(collection_capacity,
collection_frequency)`. The collector's fallback, used only by direct construction, now falls
back to the per-tick value too. One vehicle carrying one day's capacity per daily trip has an
annual throughput equal to annual collection capacity, as before, when one vehicle carried
`collection_capacity` per 12-day trip. The three-vehicle fleet keeps its size, so its headroom
over the capacity clamp keeps the same ratio.

**e. Transport cost and emissions per m³.**

- Collection emissions are `volume * distance * factor`, so per m³ they depend on the
  distance mix only, not on trip count.
- The variable cost (`distance * COLLECTION_COST_PER_KM_PER_M3 * volume`) is per m³ as well.
- `transport_cost` is a **fixed per-trip charge** (capped at 100), charged on loaded trips and
  also on empty trips.
- Daily ticks mean about 12× more trips carrying about 1/12 the volume each, so the fixed
  component per m³ rises.

The charge is kept as specified. The change in transport cost per m³ is quantified in the
stage-1 comparison (see Consequences).

**f. Other tick-tied constants.**

- `CONSUMPTION_INTERVAL_DAYS = 7`: unchanged. Market consumption is the exogenous demand clock.
- `BULLWHIP_BIN_WIDTH_DAYS = 7`: unchanged, per spec. Weekly bins still match the consumption
  tick, which is the denominator anchor (ADR 0004).
- Monitor sampling and holding cost (ADR 0017): already daily, so unaffected.
- Failure rolls: already daily (b96b320).
- RECOVERING duration and the ON_DEMAND collector adaptive threshold: measured in simulation
  days, not ticks, so unaffected.
- Collection-center storage: see above; not rescaled.
- `utilization_history` (window of 10 samples) now spans 10 days instead of about 10 cycles.
  It is written but never read (checked by grep of `core/` and `analysis/`), so it has no
  effect. Noted for later.

## Consequences

- **Mass-balance checker gap exposed and fixed** (commit "Count queued and in-flight
  repositioning in mass balance"). Daily ticks leave cross-region repositioning in mid-pipeline
  at t = 365: volume is debited at the origin before any vehicle picks it up. Neither waste
  check counted it (38.94 m³ residual in `test_landfill_ledger`). The gap existed before; the
  24-day cadence just rarely left a request queued at the horizon.
- **PUSH stops landfilling at seed 7.** At seed 7, all three PUSH combos landfill 0 m³ in
  Baseline and GenerationSurge. PULL combos landfill 2.7k-17.5k m³. `test_landfill_ledger`
  moved to PULL / ON_DEMAND to keep a non-zero ledger. This fits coupling c's roughly +20%
  effective PUSH collection capacity, which drains generator storage before it overflows.
- **Stage-1 comparison.** Reference: c12839b, `outputs/stage1/ref_n100`. New:
  `outputs/stage1/new_n100`. The table is in `docs/plans/stage1-daily-clock-results.md`.
- Out of scope, left for stages 2-4: capacity-loss failures, collector fleets, the
  working-day calendar, continuous seasonality.
