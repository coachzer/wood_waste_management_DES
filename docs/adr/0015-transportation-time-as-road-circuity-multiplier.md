# transportation_time is a road-circuity multiplier on great-circle distance

Date: 2026-06-10
Status: accepted

## Context

The scenario parameter `transportation_time` was passed through `ScenarioConfig`
and `UncertaintySet`, but nothing read it. Collector trips and transport-manager
repositioning both computed travel time as raw great-circle distance divided by
`TRAVEL_SPEED_KMH`. Meanwhile, the distance matrix is great-circle
(straight-line), which understates real road distance, and therefore travel
time, by roughly 30-40% for Slovenian routes. One parameter could fix both the
unused setting and the documented systematic bias.

## Decision

Wire `transportation_time = (mean, std)` in as a **road-circuity factor**, a
per-trip multiplier on the great-circle distance applied before dividing by
travel speed.

- **Collection trips** (`CollectorCompany._calculate_travel_time_to_generator`)
  draw a stochastic factor per trip, `Normal(mean, std)`, clamped to `>= 1.0`,
  because a road cannot be shorter than the great-circle line. The draw uses the
  collector's own seeded per-entity RNG, which keeps CRN reproducibility.
- **Repositioning trips** (`PointToPointTransport._create_transport`) apply
  the deterministic mean, clamped to `>= 1.0`, on both the pickup leg and the
  main leg. The asymmetry is deliberate. The transport manager is a single shared
  object with no seeded RNG of its own, and adding one for a secondary flow
  would add more reproducibility risk than the realism is worth.
- **Time only.** Transport cost and emissions stay on the raw great-circle
  distance. Correcting those is a separate calibration with its own literature
  factors (closer to ADR 0013). Mixing it in here would change the cost and
  emissions baselines under a parameter named "time", which readers would not
  expect.
- **Baseline recalibrated** from `(2.0, 0.2)` to `(1.35, 0.1)`. The old value
  was an arbitrary "fast, predictable transport" placeholder that was never
  applied. 1.35 falls in the documented 30-40% road-vs-great-circle
  understatement band, so the parameter now corrects the known bias instead of
  doubling it.

## Consequences

- Behavior changes on purpose (VERIFY class without byte-compare). Travel times
  grow about 35% on collection and repositioning, so collection throughput,
  vehicle utilization and time-coupled KPIs shift. No byte-identity with prior
  runs is expected. Regenerate baselines.
- Cost and emissions KPIs still carry the great-circle understatement, which
  remains a stated paper limitation
  (`project_distance_matrix_is_great_circle`).
- The numbering jumps 0011 -> 0014 -> 0015, because 0012/0013 are reserved by
  drafts not yet accepted into this directory.
