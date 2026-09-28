# Pooled robustness variant emits both echelon keys despite the Treatment identity

> Treatment-side numbers refined by ADR 0009. `treatment_anchored_pooled` read the old `collector -> treatment`
> repositioning series, so it is invalid as published until it is re-run on the corrected flow (issue 12),
> as is `treatment_stage`, which has the same value. `collector_anchored_pooled` is unaffected. The body
> keeps its original meaning.

ADR 0004 specified a "pooled robustness check": the anchored throughput-bullwhip ratios recomputed on a
system-pooled per-echelon series (all nodes summed before CV²), as a conservative lower bound on the
per-node volume-weighted headline. Issue 05 (`.scratch/bullwhip/issues/05-pooled-robustness-variant.md`)
implements it as `bullwhip.treatment_anchored_pooled` and `bullwhip.collector_anchored_pooled`. Issue 04
had already introduced the pooled per-echelon series and the `stage_bullwhip` diagnostic (ADR 0006), which
makes one of issue 05's two deliverables numerically redundant. This ADR records how the overlap is
handled. It extends ADR 0004's "pooled robustness check" clause and sits beside ADR 0006, superseding
neither.

## The redundancy

The pooled Treatment anchored ratio and the diagnostic `treatment_stage` are the same number by
construction:

```
treatment_anchored_pooled = CV²(pooled collector→treatment inbound) / CV²(consumption attempted)
treatment_stage           = CV²(pooled collector→treatment inbound) / CV²(consumption attempted)
```

ADR 0006 anticipated this. `treatment_stage` is the *pooled* Treatment ratio, and "issue 05's pooled
robustness variant will report [that quantity] directly." So `treatment_anchored_pooled` is a KPI key
whose per-run value always equals an existing key.

The Collector echelon has no such coincidence. `collector_anchored_pooled` matches no single stage. It
equals the telescoped product `treatment_stage × collector_stage` (the pooled treatment-inbound CV²
cancels; ADR 0006), which is `CV²(pooled generator→collector inbound) / CV²(consumption attempted)`.

## Decision

Emit **both** pooled keys, `treatment_anchored_pooled` and `collector_anchored_pooled`, even though the
first duplicates `treatment_stage`'s value.

The keys belong to three groups. Readers compare keys within a group, not across groups:

- `treatment_anchored` / `collector_anchored` are the per-node volume-weighted **headlines**.
- `treatment_anchored_pooled` / `collector_anchored_pooled` are their **pooled robustness lower bounds**,
  read as a parallel pair beside the headlines (the paper's robustness row).
- `treatment_stage` / `collector_stage` are the **decomposition** that shows where amplification enters.

`treatment_anchored_pooled == treatment_stage` is a *fact about the data*, not duplicated logic. The
Treatment echelon's pooled ratio is both its robustness bound and its first decomposition stage. Both keys
are thin calls onto the single `_pooled_inbound_bins` series, so there is one computation, exposed under
the name each group of readers expects. A test asserts the identity, so if the two ever diverge, that is a
regression, not drift.

## Rejected alternatives

- **Emit only `collector_anchored_pooled` and tell readers to use `treatment_stage` for the Treatment
  pooled value.** Rejected because it breaks the parallel `{treatment,collector}_anchored_pooled` naming
  that the results table reads as a pair, and it forces a lookup across groups (the robustness row reaching
  into the decomposition row) for one echelon only. Saving one key is not worth the asymmetry. It also
  departs from issue 05's literal acceptance criteria, which name both keys.
- **Define `treatment_anchored_pooled` as an alias or reference to `treatment_stage`.** Rejected because
  the per-run KPI dict is flat data consumed by the MC aggregation (issues 06/07). An alias adds indirection
  there for no gain, and a plain duplicated scalar is simpler than a reference the aggregator must resolve.
- **Drop `treatment_stage` now that the pooled variant exists.** Rejected as out of scope (ADR 0006 owns
  the stage diagnostic) and wrong, because `collector_stage` cannot be derived from the anchored and pooled
  keys alone, so the decomposition pair must stay intact.

## Consequence

The `bullwhip` namespace carries one numerically redundant key by design. Downstream MC aggregation
(issues 06/07) treats all bullwhip keys the same way, so it picks up the pooled pair automatically. The
redundancy costs one column and no branching. Anyone who compares `treatment_anchored_pooled` with
`treatment_stage` and finds them equal is seeing the intended identity, not a bug.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md`: the parent decision. This ADR extends its "pooled
  robustness check" clause.
- `docs/adr/0006-stage-bullwhip-telescopes-at-pooled-aggregation.md`: establishes that `treatment_stage` is
  the pooled Treatment ratio and that the stages telescope only at the pooled aggregation. This ADR records
  the key-overlap decision that ADR 0006 anticipated.
