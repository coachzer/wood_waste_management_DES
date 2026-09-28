# Stage-by-stage bullwhip telescopes at the pooled aggregation, not the per-node headline

> Treatment-side numbers refined by ADR 0009. `treatment_stage`'s numerator and `collector_stage`'s
> denominator read the old `collector -> treatment` series, which measured repositioning, not intake. The
> telescoping identity below still holds (the repositioning term cancels in the product), but each stage
> factor is invalid as published until it is re-run on the corrected flow (issue 12). The body keeps its
> original meaning.

ADR 0004 specified a "stage-by-stage diagnostic" beside the anchored headline: Treatment stage =
`CV²(treatment inbound)/CV²(consumption)`, Collector stage = `CV²(collector inbound)/CV²(treatment
inbound)`, and it claimed that "the stage ratios telescope to the anchored values." Implementing issue 04
(`.scratch/done/bullwhip/issues/04-stage-by-stage-diagnostic.md`) showed that this claim does not say which
*aggregation level* it means, and it is true at only one of the two candidate levels. This ADR fixes which
one and records why. It refines ADR 0004's stage-diagnostic clause and leaves the rest of that decision in
place.

## The ambiguity

ADR 0004's headline anchored metrics (`treatment_anchored`, `collector_anchored`) are computed **per node,
then volume-weighted averaged across the nodes of the echelon**. This is deliberate. A tiny-flow node whose
CV² explodes as its mean approaches zero cannot dominate, and out-of-phase (s,S) reorder spikes are kept
instead of smoothed (ADR 0004, "per-node CV² then volume-weighted average").

The stage definitions, written as bare `CV²(treatment inbound)`, assume a **single** CV² value per echelon.
An echelon reduced by per-node-then-weighted-average has no single CV². That aggregation produces a
weighted average of *ratios*, not a ratio of two well-defined CV² scalars. And the telescoping arithmetic
breaks under the weighted average:

```
treatment_stage × collector_stage
  = weighted_avgₙ[CV²(Tₙ)/CV²(C)] × weighted_avgₙ[CV²(Coₙ)/CV²(Tₙ)]
  ≠ weighted_avgₙ[CV²(Coₙ)/CV²(C)]   = collector_anchored   (per-node headline)
```

because a product of weighted averages is not the weighted average of products. So the identity the issue
asks the test to *prove* does **not** hold against the per-node headline KPIs at any honest tolerance.
Two ways to force the test green were rejected: loosening the tolerance, and defining `collector_stage` as
the derived quotient `collector_anchored / treatment_anchored`. The quotient is not a flow CV² ratio in any
node sense, and it would stop the diagnostic from doing its only job, which is showing *where*
amplification enters.

## Decision

The stage-by-stage diagnostic is computed on **system-pooled** per-echelon series. All of an echelon's
inbound flows are summed into one weekly series before CV², so each echelon has a single CV² scalar.

```
treatment_stage = CV²(pooled collector→treatment weekly inbound) / CV²(weekly consumption attempted)
collector_stage = CV²(pooled generator→collector weekly inbound) / CV²(pooled collector→treatment weekly inbound)
```

At this aggregation the identity is **exact by construction**. The pooled treatment-inbound CV² in
`treatment_stage`'s numerator is the *same scalar* as in `collector_stage`'s denominator, so it cancels:

```
treatment_stage × collector_stage
  = [CV²(T)/CV²(C)] × [CV²(Co)/CV²(T)] = CV²(Co)/CV²(C)   = the pooled collector anchored ratio
```

The test checks this equality at `rel_tol≈1e-9` against a pooled collector anchored ratio recomputed
directly, not against the per-node `collector_anchored` headline, which telescoping does not reach.

The weekly binning, warm-up window and `attempted` anchor are reused from ADR 0004 (`_weekly_bins`,
`BULLWHIP_WARMUP_WEEKS`, `WEEKS_PER_YEAR`). Pooling only means feeding all of the echelon's flows into one
bin series instead of grouping by node, so there is no second binning scheme (issue 04 "no re-binning").

The stages are emitted as `bullwhip.treatment_stage` and `bullwhip.collector_stage` in the per-run KPI
namespace, beside the existing anchored ratios and the floor.

## Why pooled is the right level for a *diagnostic* (the rejected alternatives)

- **Per-node-weighted (the headline level), rejected for the stages.** It is correct for the *headline*
  amplification number, because it keeps the lumpy per-node reorder mechanism that carries the bullwhip
  signal. But it cannot support a telescoping decomposition, which is the diagnostic's whole purpose. You
  cannot attribute "where amplification enters" to a stage if the stages do not compose to the whole. The
  headline and the diagnostic answer different questions, so they can use different aggregations.

- **Defining `collector_stage := collector_anchored / treatment_anchored`, rejected.** This forces the
  identity to hold against the per-node headline by construction, but the resulting `collector_stage` is a
  quotient of two cross-echelon weighted averages, not `CV²(collector inbound)/CV²(treatment inbound)` at
  any aggregation. It would report a number that looks like a stage ratio but shows nothing about where
  amplification enters.

- **Consequence.** `treatment_stage` therefore does **not** equal the per-node `treatment_anchored`
  headline. The issue text's parenthetical "identical to the anchored Treatment value" is true only at
  pooled aggregation, and the headline is not pooled. The gap between them is exactly the per-node-vs-pooled
  spread ADR 0004 already flagged: pooling smooths out-of-phase spikes and so *understates* the per-node
  amplification. The `treatment_stage ≤ treatment_anchored` gap is itself a reportable measure of how out of
  phase the nodes are, and issue 05's pooled robustness variant will report that quantity directly. Issue 04
  introduces the pooled per-echelon series, and issue 05 reuses it.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md`: the parent decision. This ADR refines its
  "stage-by-stage diagnostic" clause and its claim that "the stage ratios telescope to the anchored values",
  which holds at the pooled aggregation level, not at the per-node-volume-weighted headline.
- `fransooMeasuringBullwhipEffect2000`: Fransoo & Wouters (2000). The per-node-vs-pooled aggregation
  concern this ADR depends on is the same one ADR 0004 cites for the headline split.
