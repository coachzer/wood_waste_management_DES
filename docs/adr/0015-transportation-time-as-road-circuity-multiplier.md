# transportation_time is a road-circuity multiplier on great-circle distance

Date: 2026-06-10
Status: accepted

## Context

The scenario knob `transportation_time` was carried through `ScenarioConfig`
and `UncertaintySet` but nothing read it: collector trips and transport-manager
repositioning both computed travel time as raw great-circle distance over
`TRAVEL_SPEED_KMH`. Meanwhile, the distance matrix is great-circle
(straight-line), which understates real road distance — and therefore travel
time — by roughly 30-40% for Slovenian routes. A half-wired knob and a
documented systematic bias, fixable by the same parameter.

## Decision

Wire `transportation_time = (mean, std)` in as a **road-circuity factor**: a
per-trip multiplier on the great-circle distance before dividing by travel
speed.

- **Collection trips** (`CollectorCompany._calculate_travel_time_to_generator`)
  draw a stochastic factor per trip: `Normal(mean, std)`, clamped to `>= 1.0`
  — a road cannot be shorter than the great-circle line. The draw uses the
  collector's own seeded per-entity RNG, preserving CRN reproducibility.
- **Repositioning trips** (`PointToPointTransport._create_transport`) apply
  the deterministic mean, clamped to `>= 1.0`, on both the pickup leg and the
  main leg. Deliberate asymmetry: the transport manager is a single shared
  object with no seeded RNG of its own, and threading one through it for a
  secondary flow is not worth the reproducibility surface.
- **Time-only scope**: transport cost and emissions stay on the raw
  great-circle distance. Correcting those is a separate calibration with its
  own literature factors (and ADR 0013 territory); conflating it here would
  silently change the cost/emissions baselines under a knob named "time".
- **Baseline recalibrated** from `(2.0, 0.2)` to `(1.35, 0.1)`: the old value
  was an arbitrary "fast, predictable transport" placeholder never applied;
  1.35 sits in the documented 30-40% road-vs-great-circle understatement
  band, so the knob now corrects the known bias instead of doubling it.

## Consequences

- Deliberately behavior-changing (VERIFY class without byte-compare): travel
  times lengthen ~35% on collection and repositioning, so collection
  throughput, vehicle utilization, and time-coupled KPIs shift. No
  byte-identity with prior runs is expected; regenerate baselines.
- Cost and emissions KPIs still carry the great-circle understatement; that
  remains a stated paper limitation
  (`project_distance_matrix_is_great_circle`).
- The numbering jumps 0011 -> 0014 -> 0015: 0012/0013 are reserved by drafts
  not yet accepted into this directory.
