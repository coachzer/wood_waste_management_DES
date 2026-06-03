# Pooled robustness variant emits both echelon keys despite the Treatment identity

ADR 0004 specified a "pooled robustness check": the anchored throughput-bullwhip ratios recomputed on a
system-pooled per-echelon series (all nodes summed before CV²) as a conservative lower bound on the per-node
volume-weighted headline. Issue 05 (`.scratch/bullwhip/issues/05-pooled-robustness-variant.md`) implements
it as `bullwhip.treatment_anchored_pooled` and `bullwhip.collector_anchored_pooled`. But issue 04 had
already introduced the pooled per-echelon series and the `stage_bullwhip` diagnostic (ADR 0006), and that
makes one of issue 05's two deliverables numerically redundant. This ADR records how the overlap is handled.
It extends ADR 0004's "pooled robustness check" clause and sits beside ADR 0006; it supersedes neither.

## The redundancy

The pooled Treatment anchored ratio and the diagnostic `treatment_stage` are, by construction, the same
number:

```
treatment_anchored_pooled = CV²(pooled collector→treatment inbound) / CV²(consumption attempted)
treatment_stage           = CV²(pooled collector→treatment inbound) / CV²(consumption attempted)
```

ADR 0006 already foreshadowed this — `treatment_stage` is the *pooled* Treatment ratio, and "issue 05's
pooled robustness variant will report [that quantity] directly." So shipping `treatment_anchored_pooled`
emits a KPI key whose per-run value always equals an existing key.

The Collector echelon has no such coincidence: `collector_anchored_pooled` matches no single stage. It
equals the telescoped product `treatment_stage × collector_stage` (the pooled treatment-inbound CV² cancels;
ADR 0006), i.e. `CV²(pooled generator→collector inbound) / CV²(consumption attempted)`.

## Decision

Emit **both** pooled keys — `treatment_anchored_pooled` and `collector_anchored_pooled` — even though the
former duplicates `treatment_stage`'s value.

The two keys belong to different conceptual groups that are read together within their group, not across:

- `treatment_anchored` / `collector_anchored` — the per-node volume-weighted **headlines**.
- `treatment_anchored_pooled` / `collector_anchored_pooled` — their **pooled robustness lower bounds**, read
  as a parallel pair beside the headlines (the paper's robustness row).
- `treatment_stage` / `collector_stage` — the **decomposition** that localizes where amplification enters.

`treatment_anchored_pooled == treatment_stage` is a *fact about the data* (the Treatment echelon's pooled
ratio is simultaneously its robustness bound and its first decomposition stage), not duplicated logic: both
keys are thin calls onto the single `_pooled_inbound_bins` series, so there is one computation, surfaced
under the name each reader group expects. The identity is asserted in a test, so if the two ever diverge
that is a regression, not drift.

## Rejected alternatives

- **Emit only `collector_anchored_pooled`, tell readers to use `treatment_stage` for the Treatment pooled
  value.** Rejected: it breaks the parallel `{treatment,collector}_anchored_pooled` naming the results table
  reads as a pair, and forces a cross-group lookup (robustness row reaching into the decomposition row) for
  one echelon only. The saved key is not worth the asymmetry. It also deviates from issue 05's literal
  acceptance criteria, which name both keys.
- **Define `treatment_anchored_pooled` as an alias/reference to `treatment_stage`.** Rejected: the per-run
  KPI dict is flat data consumed by the MC aggregation (issues 06/07); an alias adds indirection there for no
  gain, and a plain duplicated scalar is simpler than a reference the aggregator must resolve.
- **Drop `treatment_stage` now that the pooled variant exists.** Rejected: out of scope (ADR 0006 owns the
  stage diagnostic) and wrong — `collector_stage` is not derivable from the anchored/pooled keys alone, so
  the decomposition pair must stay intact.

## Consequence

The `bullwhip` namespace carries one numerically-redundant key by design. Downstream MC aggregation (issues
06/07) treats all bullwhip keys uniformly, so it picks up the pooled pair automatically; the redundancy costs
one column, not any branching. Anyone comparing `treatment_anchored_pooled` against `treatment_stage` and
finding them equal is seeing the intended identity, not a bug.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md` — the parent decision; this ADR extends its "pooled
  robustness check" clause.
- `docs/adr/0006-stage-bullwhip-telescopes-at-pooled-aggregation.md` — establishes that `treatment_stage` is
  the pooled Treatment ratio and that the stages telescope only at the pooled aggregation; this ADR records
  the consequent key-overlap decision it foreshadowed.
