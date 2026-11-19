# Operational realism, later stages

Follow-ups to the daily operating clock (ADR 0020 in `docs/decisions.md`).

- **Repositioning ignores vehicle capacity.** `PointToPointTransport._create_transport` loads the full `request.volume` onto one vehicle. Vehicle capacity is one tick of collection, so a load can be many times it. Fold into stage 3.
- **Stage 2, capacity-loss failures.** Failures reduce capacity instead of only skipping ticks.
- **Stage 3, collector fleets.** Make vehicle count and size data. `collection_capacity` clamps each trip, not each tick (`collect_from_generator`), so three vehicles can move 3x the per-tick capacity.
- **Stage 4, working-day calendar and continuous seasonality.** Replace the quarter-step Seasonal Pattern.
- **PULL backlog vs cadence confound.** A no-carry control run would separate the daily clock from "shortfalls no longer forgotten".
- **Fixed per-trip `transport_cost`.** Charged on loaded trips only. Decide whether a fixed charge per trip, with free empty trips, is the intended cost model.
