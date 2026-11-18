# A kanban signal moves only the waste type it names

Date: 2026-11-18
Status: accepted

## Context

Under PULL, a collector serving a signal for one waste type collected from every stream the
generator held, in dict order, up to the signalled volume. A signal for 15 01 03 could come back
as 03 01 05, so the OSB inputs were fetched only when they happened to come first.

## Decision

`collect_from_generator` and `_perform_collection_at_site` take an optional `waste_type`. A
signalled pickup passes the signal's type and is capped by that stream's volume. PUSH pickups pass
none and still take every stream.

## Consequences

Paired change against ADR 0027, seeds 1-10, Baseline. PUSH is unchanged (identical runs).

| Combo | Service level, % | Collection rate, % | Total system cost, EUR |
|---|---|---|---|
| PULL ON_DEMAND | -1.1 [-3.6, +1.5] | -0.5 [-0.9, -0.04] | +0.07 M [-0.41, +0.55] |
| PULL REORDER_50 | +0.4 [+0.2, +0.7] | +0.1 [-0.2, +0.5] | -0.13 M [-0.18, -0.08] |
| PULL REORDER_90 | +2.7 [+2.2, +3.2] | +0.7 [+0.4, +1.1] | +0.37 M [+0.23, +0.50] |

PULL REORDER_50 and REORDER_90 now reach about 100% service.

### PULL ON_DEMAND is still about 12 points short (open finding)

This fix does not move it. Probes on pomurska, seed 1 (`.scratch/methodology/pull_*_probe.py`):

- 351 of 354 collector trips serve generator full-storage signals, and 3 trips (87 m3) serve
  pomurska's own treatment. Treatment drains 1,163 m3 of 15 01 03 a year, against 2,602 m3
  under PUSH.
- Generator signals are not the cause. Ten seeds with a scratch patch: serving treatment signals
  first gives +2.1 points [-0.8, +5.0], and ignoring generator signals gives +0.3 [-2.9, +3.6].
  Ignoring them also cuts REORDER collection by 19 points.
- Served treatment signals stay in their own region, so no waste is stranded in another center.
- What differs is trip size. ON_DEMAND orders back one day's consumption per type, so a PULL
  treatment trip carries 29 m3 on average, against 1,350 m3 for a PUSH trip and 537 m3 for a
  PULL REORDER_90 trip, with 3 vehicles per collector. That points to a transport limit under
  lot-for-lot PULL. Not confirmed: vehicle occupancy and lead time were not measured directly.

Whether a generator's full-storage call counts as a PULL trigger is part of the policy
definition and is left as it is (CLAUDE.md).
