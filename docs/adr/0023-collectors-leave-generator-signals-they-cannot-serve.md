# Collectors leave generator signals they cannot serve

Date: 2026-11-18
Status: accepted

## Context

All PULL collectors share one signal bus. In `CollectorCompany._process_kanban_signals`, a collector
whose prioritized generators did not include the signalling generator acknowledged the signal, which
removed it from every other collector's view. Collectors that could have served the signal then
never saw it.

Measured on 2af17da (seeds 1-10, Baseline), 82 to 94% of PULL generator signals were deleted this
way without anyone acting on them. Every one was deleted by a collector in another region. ADR 0021
listed the missing `target_region` on generator signals but not this deletion.

A `target_region` on generator signals would not fix it. `_get_prioritized_generators` deliberately
gives 20% of a collector's capacity (`1 - LOCAL_COLLECTION_RATIO`) to the nearest other region, so
an out-of-region collector can be a legitimate server of a generator signal.

## Decision

A collector acknowledges a generator signal only when it collects against it. If none of its
prioritized generators match, it leaves the signal on the bus. The signal still expires after
`KANBAN_SIGNAL_MAX_AGE_DAYS`. Treatment and collector signals are unchanged: an unmatched treatment
signal is still propagated upstream and acknowledged.

## Consequences

PULL generator signals deleted without action fall to 0. The share acted on changes from 6.2 / 12.6 /
9.8% to 21.1 / 9.8 / 10.5% (ON_DEMAND / REORDER_50 / REORDER_90).

Paired over seeds 1-10, PULL after minus PULL before (95% interval):

| Strategy | Full service, points | Collection rate, points | Transport cost | Emissions, kgCO2e | Collector bullwhip |
|---|---|---|---|---|---|
| ON_DEMAND | -2.80 [-4.29, -1.32] | -0.57 [-1.04, -0.10] | +409,506 [+331,685, +487,328] | +162,341 [+132,895, +191,786] | -66 [-80, -51] |
| REORDER_50 | +0.25 [-0.08, +0.59] | -0.25 [-0.73, +0.22] | +184,906 [+147,567, +222,244] | +128,874 [+120,084, +137,664] | +41 [+31, +52] |
| REORDER_90 | +0.22 [+0.01, +0.43] | -1.29 [-1.69, -0.89] | +190,773 [+139,977, +241,569] | +71,274 [+48,701, +93,847] | +16 [+5, +27] |

- **The fix costs PULL ON_DEMAND service.** Full service falls 2.8 points. REORDER_90 gains a
  marginal 0.2 points, and REORDER_50 does not change detectably.
- **Transport cost rises 8 to 18%, and emissions rise with it.** Signals that used to be deleted are
  now served, some by collectors in another region.
- **Collector bullwhip moves in both directions:** it falls for ON_DEMAND and rises for both REORDER
  strategies. Treatment bullwhip changes are within noise.
- PULL landfill stays at 0. Armed mass-balance checks pass for all three PULL strategies (seeds 1-3).
- PUSH is byte-identical on all 30 runs: PUSH collectors never process signals.
- Not confirmed: why ON_DEMAND service falls. One candidate channel is that signals now stay on the
  bus longer, and the PULL collector efficiency bonus counts every pending signal (ADR 0021's
  efficiency confound). The other is that collectors spend vehicles on cross-region pickups.
  Neither has been tested.

Probe and results: `.scratch/pushpull-followups/probes/remeasure_2026_11_18.py`, with
`remeasure/` (before) and `remeasure_after_theft_fix/` (after). Fingerprints and KPIs:
`.scratch/fixall/ref_2af17da/` and `after_02/`.
