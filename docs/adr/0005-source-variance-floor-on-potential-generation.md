# Bullwhip source-variance floor measured on potential, not committed, generation

ADR 0004 introduced the **source-variance floor** — `CV²(weekly waste generation)` — as a policy-invariant reference proving the upstream source carries no policy signal, the fixed baseline the two ordering echelons amplify above. It tacitly assumed "waste generation" is a single, unambiguous, exogenous series. Implementing issue 03 (`.scratch/bullwhip/issues/03-generation-source-variance-floor.md`) and checking that assumed invariance against a real run falsified it: the floor computed on the *committed* generation that the monitor logs is **not** policy-invariant. This ADR records the finding and fixes which generation series the floor is measured on. It refines ADR 0004's floor definition; it does not supersede the rest of that decision.

## The finding

The only generation quantity the simulation logs is `WasteMonitor.generation_history[node]["total_generated"]` — the *committed* volume, i.e. what actually entered storage. `core/generator.py::_generate_waste_for_period` caps each tick's generation at the remaining storage headroom (`potential_volume <= available_storage`); when a generator's storage is full, that tick's waste is silently dropped. Storage headroom is set by collection drainage, which is policy- and strategy-dependent. So committed generation — and the lumpiness of its weekly series — inherits a downstream policy signal.

Measured on committed generation, the floor swings across the six PUSH/PULL × strategy combos of a single CRN-seeded run from **≈0.91 to ≈1.29** (a ~30% spread), tracking a `total_generated` that ranges 1.85M–2.34M m³. A "policy-invariant reference" that moves 30% across policies is not a reference; it conflates the exogenous source with the finite-storage backpressure the echelon metric is trying to isolate, defeating the floor's entire purpose (acceptance criterion 3 of issue 03 — "near-identical across PUSH and PULL for the same seed" — fails for this real reason, not a tolerance one).

## Decision

Measure the floor on **potential** generation — the volume the exogenous source process offers each tick *before* the storage-headroom cap: `base_rate × seasonal_factor × daily_factor × efficiency`, summed across waste types. This requires instrumentation, because the pre-cap volume was previously not recorded anywhere and is not recoverable post-hoc.

- `core/generator.py` accumulates `total_potential_generated` (a per-waste-type running total mirroring `total_generated`), incremented for every waste type on every non-failed tick from the `potential_volume` already computed at the cap check.
- `WasteMonitor.track_generation` records `total_potential_generated` parallel to `total_generated` in `generation_history`.
- `monitoring.bullwhip.generation_floor_cv2` differences that cumulative series into weekly increments on the weeks 5–52 grid, sums across waste types per node, and volume-weighted-averages the per-node CV² values (identical aggregation to the echelons, but reporting a raw CV² rather than a ratio).

Measured this way the floor is **byte-identical across all six combos** at a fixed seed (observed spread 0.0; the policy-invariance guard asserts equality at `rel=1e-9`). The generator's RNG is consumed only by `_calculate_daily_factors`, whose draw count per tick is policy-independent, so the potential series is genuinely exogenous.

## Why these choices (the rejected alternatives)

- **Instrument potential, rather than reframe the committed floor as a "realized source variance" finding.** Reporting the committed floor and documenting the 30% policy coupling as a result was the no-code-change option. Rejected: the floor's job in the paper is to *anchor* the echelon ratios as a policy-invariant baseline ("amplification is injected mid-chain, the source is flat"). A floor that itself carries a policy signal cannot play that role, and presenting both a policy-coupled floor and policy-coupled echelons muddies the one clean claim the floor exists to make. The finite-storage backpressure *is* interesting, but it belongs in the echelon/Discussion analysis, not smuggled into the reference baseline.

- **Behaviour-preserving instrumentation, despite the freeze.** This is the first bullwhip slice to touch `core/` — the INDEX's standing invariant called the whole metric "purely post-hoc, zero sim changes." The instrumentation adds an accumulator and one `+=` from an already-computed value; it consumes no RNG and changes no committed volume, storage level, or control flow. The golden byte-identical exit test stays `MATCH` in `--mode additive` (300 pure additions across 60 runs, zero changed existing keys), and the cross-process determinism guard stays byte-identical. So the *behaviour contract* the freeze protects is intact; what grew is the recorded surface, which is exactly what the analysis layer is permitted to do. The honest consequence, recorded here: "post-hoc only" is no longer literally true of the floor — it required a minimal, verified source-side probe.

- **A separate `total_potential_generated` accumulator, not a reconstruction.** Potential generation cannot be recovered from the persisted logs: `volumes` records current stock (not the per-tick increment), and `total_generated` is already the capped quantity. Differencing either reconstructs committed, not potential, generation. The pre-cap value exists only at the moment of the cap check, so capturing it there is the only faithful option.

## Consequence for the reported numbers

The potential-based floor is a much smaller CV² (≈0.025 at the reference seed) than the committed series produced (≈0.9–1.3), because potential generation is a smooth seasonal-plus-noise process while committed generation was lumpy with saturation dropouts. This is the intended behaviour: a low, flat source-variance floor that the Treatment and Collector echelon ratios sit well above is precisely the "amplification injected in the middle of the chain" story ADR 0004 predicted. The committed-vs-potential gap (generation dropped to landfill under storage pressure) is itself a reportable property of the supply-driven chain, but it is an *echelon/throughput* observation, not a source-variance one.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md` — the parent decision; this ADR refines its "source-variance floor (reference, not an echelon)" clause and the "generation CV² is a policy-invariant seasonal baseline" claim, which holds only for potential generation.
- `fransooMeasuringBullwhipEffect2000` — Fransoo & Wouters (2000). The CV²-normalized measure and the aggregation-level concern carried over unchanged from ADR 0004.
