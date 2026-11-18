# PUSH and PULL collectors differ only in their trigger

Date: 2026-11-18
Status: accepted

## Context

A PUSH versus PULL comparison is only internally valid if the two policies differ in the
decision rule under study, the collection trigger, and nothing else. ADR 0021 and ADR 0022 listed
two confounds that remained:

- Collector efficiency came from six hand-set curves, one per policy and strategy
  (`collector_push_efficiency`, `collector_pull_efficiency`). Some PULL curves added a bonus per
  pending signal, so PULL collectors also worked faster, not just at different times.
- A PULL collector with no signal still collected by volume when its center was below
  `max(0.15, adaptive - 0.15)`. That is a PUSH rule inside PULL, against the kanban rule that no
  material moves without a signal.

## Decision

- Collector efficiency is equipment aging only, `max(floor, 1 - t * rate)`, identical for all six
  combinations. The curves, their 24 constants, and the policy's clamping wrapper are removed.
- A PULL collector collects only when it holds a non-market signal, and still only below the
  utilization ceiling (ADR 0022). With no signal it does nothing.
- PUSH is unchanged: it collects by volume below `min(ceiling, adaptive + buffer)`.

Out of scope, still different per strategy: the collector adaptive threshold and the generator
signal thresholds. The ON_DEMAND adaptive threshold grows with absolute simulation time
(`base_time = env.now`), not time since some event; this is flagged, not changed.

## Consequences

Paired over seeds 1-10, Baseline, against the previous commit: no KPI moved by more than about 1%
of its level, and most paired 95% CIs include zero. The removed curves were near 1.0 over the
utilization ranges the runs visit. Largest movements:

- PULL ON_DEMAND collection transport cost +62,600 EUR [+39,800, +85,400] (+2.4%).
- PULL REORDER_50 total system cost +86,000 EUR [+40,400, +131,600] (+0.4%), uncollected volume
  -14,400 m3 [-22,500, -6,300].
- PUSH REORDER_50 and REORDER_90 collection transport cost about -1%.

PULL collection did not stall: the collection rate stays at 29 to 31% of potential generation for
all three strategies, so treatment reorder signals alone keep collectors supplied.

Service level, landfill (still 0) and every bullwhip ratio are unchanged within their CIs.
