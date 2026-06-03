# Stage-by-stage bullwhip telescopes at the pooled aggregation, not the per-node headline

ADR 0004 specified a "stage-by-stage diagnostic" alongside the anchored headline: Treatment stage =
`CV²(treatment inbound)/CV²(consumption)`, Collector stage = `CV²(collector inbound)/CV²(treatment
inbound)`, with the claim that "the stage ratios telescope to the anchored values." Implementing issue 04
(`.scratch/bullwhip/issues/04-stage-by-stage-diagnostic.md`) surfaced that this telescoping claim is
ambiguous about *aggregation level*, and is only true at one of the two candidate levels. This ADR pins
which one and records why. It refines ADR 0004's stage-diagnostic clause; it does not supersede the rest of
that decision.

## The ambiguity

ADR 0004's headline anchored metrics (`treatment_anchored`, `collector_anchored`) are computed **per node,
then volume-weighted-averaged across the nodes of the echelon** — deliberately, so a tiny-flow node whose
CV² explodes as its mean approaches zero cannot dominate, and so out-of-phase (s,S) reorder spikes are
preserved rather than smoothed (ADR 0004, "per-node CV² then volume-weighted average").

The stage definitions, written as bare `CV²(treatment inbound)`, presuppose a **single** CV² value per
echelon. There is no single CV² for an echelon that is reduced by per-node-then-weighted-average: that
aggregation produces a weighted average of *ratios*, not a ratio of two well-defined CV² scalars. And the
telescoping arithmetic does not survive the weighted average:

```
treatment_stage × collector_stage
  = weighted_avgₙ[CV²(Tₙ)/CV²(C)] × weighted_avgₙ[CV²(Coₙ)/CV²(Tₙ)]
  ≠ weighted_avgₙ[CV²(Coₙ)/CV²(C)]   = collector_anchored   (per-node headline)
```

because a product of weighted averages is not the weighted average of products. So the identity the issue
asks the test to *prove* does **not** hold against the per-node headline KPIs — at any tolerance that isn't
a fudge. (Forcing it green by loosening the tolerance, or by defining `collector_stage` as the derived
quotient `collector_anchored / treatment_anchored`, was rejected: the latter is not a flow CV² ratio in any
node sense and destroys the diagnostic's only job — localizing *where* amplification enters.)

## Decision

The stage-by-stage diagnostic is computed on **system-pooled** per-echelon series: all of an echelon's
inbound flows are summed into one weekly series before CV², so each echelon is a single CV² scalar.

```
treatment_stage = CV²(pooled collector→treatment weekly inbound) / CV²(weekly consumption attempted)
collector_stage = CV²(pooled generator→collector weekly inbound) / CV²(pooled collector→treatment weekly inbound)
```

At this aggregation the identity is **exact by construction**: the pooled treatment-inbound CV² that sits
in `treatment_stage`'s numerator is the *same scalar* that sits in `collector_stage`'s denominator, so it
cancels:

```
treatment_stage × collector_stage
  = [CV²(T)/CV²(C)] × [CV²(Co)/CV²(T)] = CV²(Co)/CV²(C)   = the pooled collector anchored ratio
```

The test proves this equality at `rel_tol≈1e-9` against a directly recomputed pooled collector anchored
ratio — not against the per-node `collector_anchored` headline, which telescoping does not reach.

The same weekly binning, warm-up window, and `attempted` anchor as ADR 0004 are reused (`_weekly_bins`,
`BULLWHIP_WARMUP_WEEKS`, `WEEKS_PER_YEAR`) — pooling is just "feed all of the echelon's flows to one bin
series" rather than grouping by node, so there is no second binning scheme (issue 04 "no re-binning").

Emitted as `bullwhip.treatment_stage` and `bullwhip.collector_stage` in the per-run KPI namespace, beside
the existing anchored ratios and the floor.

## Why pooled is the right level for a *diagnostic* (the rejected alternatives)

- **Per-node-weighted (the headline level) — rejected for the stages.** It is correct for the *headline*
  amplification number (it preserves the lumpy per-node reorder mechanism the bullwhip signal lives in).
  But it cannot carry a telescoping decomposition, which is the diagnostic's entire purpose: you cannot
  attribute "where amplification enters" to a stage if the stages do not compose to the whole. The headline
  and the diagnostic answer different questions, so they legitimately use different aggregations.

- **Defining `collector_stage := collector_anchored / treatment_anchored` — rejected.** This forces the
  identity to hold against the per-node headline by construction, but the resulting `collector_stage` is a
  quotient of two cross-echelon weighted averages, not `CV²(collector inbound)/CV²(treatment inbound)` in
  any aggregation. It would report a number that looks like a stage ratio but localizes nothing.

- **Consequence, stated honestly.** `treatment_stage` therefore does **not** equal the per-node
  `treatment_anchored` headline (the issue text's parenthetical "identical to the anchored Treatment value"
  is true only at pooled aggregation, which the headline is not). The gap between them is exactly the
  per-node-vs-pooled spread ADR 0004 already flagged — pooling smooths out-of-phase spikes and so
  *understates* the per-node amplification. That `treatment_stage ≤ treatment_anchored` gap is itself a
  reportable read on how out-of-phase the nodes are, and it is precisely the quantity issue 05's pooled
  robustness variant will report directly. Issue 04 introduces the pooled per-echelon series; issue 05
  reuses it.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md` — the parent decision; this ADR refines its
  "stage-by-stage diagnostic" clause and the "stage ratios telescope to the anchored values" claim, which
  holds at the pooled aggregation level, not the per-node-volume-weighted headline.
- `fransooMeasuringBullwhipEffect2000` — Fransoo & Wouters (2000). The per-node-vs-pooled aggregation
  concern this ADR turns on is the same one ADR 0004 cites for the headline split.
