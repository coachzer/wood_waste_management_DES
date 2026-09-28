# Bullwhip source-variance floor measured on potential, not committed, generation

ADR 0004 introduced the **source-variance floor**, `CV²(weekly waste generation)`, as a policy-invariant reference showing that the upstream source carries no policy signal. It is the fixed baseline the two ordering echelons amplify above. ADR 0004 assumed without saying so that "waste generation" is a single, unambiguous, exogenous series. Implementing issue 03 (`.scratch/done/bullwhip/issues/03-generation-source-variance-floor.md`) and checking that invariance against a real run disproved it. The floor computed on the *committed* generation that the monitor logs is **not** policy-invariant. This ADR records the finding and fixes which generation series the floor uses. It refines ADR 0004's floor definition and leaves the rest of that decision in place.

## The finding

The only generation quantity the simulation logs is `WasteMonitor.generation_history[node]["total_generated"]`, the *committed* volume, meaning what actually entered storage. `core/generator.py::_generate_waste_for_period` caps each tick's generation at the remaining storage headroom (`potential_volume <= available_storage`). When a generator's storage is full, that tick's waste is dropped without any record. Collection drainage sets storage headroom, and drainage depends on policy and strategy. So committed generation, and the lumpiness of its weekly series, inherits a downstream policy signal.

Measured on committed generation, the floor swings from **about 0.91 to about 1.29** (a spread of about 30%) across the six PUSH/PULL × strategy combos of a single CRN-seeded run, tracking a `total_generated` that ranges from 1.85M to 2.34M m³. A "policy-invariant reference" that moves 30% across policies is not a reference. It mixes the exogenous source with the finite-storage backpressure that the echelon metric is trying to isolate, which defeats the floor's purpose. Acceptance criterion 3 of issue 03 ("near-identical across PUSH and PULL for the same seed") fails for this real reason, not because of a tolerance setting.

## Decision

Measure the floor on **potential** generation, the volume the exogenous source process offers each tick *before* the storage-headroom cap: `base_rate × seasonal_factor × daily_factor × efficiency`, summed across waste types. This needs new instrumentation, because the pre-cap volume was not recorded anywhere and cannot be recovered afterwards.

- `core/generator.py` accumulates `total_potential_generated`, a per-waste-type running total that mirrors `total_generated`. It is incremented for every waste type on every non-failed tick from the `potential_volume` already computed at the cap check.
- `WasteMonitor.track_generation` records `total_potential_generated` next to `total_generated` in `generation_history`.
- `monitoring.bullwhip.generation_floor_cv2` differences that cumulative series into weekly increments on the weeks 5-52 grid, sums across waste types per node, and takes the volume-weighted average of the per-node CV² values. The aggregation is identical to the echelons, but it reports a raw CV² instead of a ratio.

Measured this way, the floor is **byte-identical across all six combos** at a fixed seed (observed spread 0.0; the policy-invariance guard asserts equality at `rel=1e-9`). Only `_calculate_daily_factors` draws from the generator's RNG, and its draw count per tick does not depend on policy, so the potential series is truly exogenous.

## Why these choices (the rejected alternatives)

- **Instrument potential generation instead of reframing the committed floor as a "realized source variance" finding.** Reporting the committed floor and documenting the 30% policy coupling as a result was the option with no code change. Rejected because the floor's job in the paper is to *anchor* the echelon ratios as a policy-invariant baseline ("amplification enters mid-chain, the source is flat"). A floor that carries its own policy signal cannot do that, and showing a policy-coupled floor next to policy-coupled echelons blurs the one clean claim the floor exists to make. The finite-storage backpressure *is* interesting, but it belongs in the echelon and Discussion analysis, not hidden inside the reference baseline.

- **Behaviour-preserving instrumentation, despite the freeze.** This is the first bullwhip slice to touch `core/`, and the INDEX's standing invariant called the whole metric "purely post-hoc, zero sim changes." The instrumentation adds an accumulator and one `+=` from a value already computed. It consumes no RNG and changes no committed volume, storage level or control flow. The golden byte-identical exit test stays `MATCH` in `--mode additive` (300 pure additions across 60 runs, zero changed existing keys), and the cross-process determinism guard stays byte-identical. The *behaviour contract* the freeze protects is therefore intact. Only the set of recorded fields grew, which the analysis layer is allowed to do. The consequence, recorded here: "post-hoc only" is no longer literally true of the floor, since it needed a small, verified probe in the source.

- **A separate `total_potential_generated` accumulator, not a reconstruction.** Potential generation cannot be recovered from the persisted logs. `volumes` records current stock (not the per-tick increment), and `total_generated` is already capped. Differencing either one reconstructs committed generation, not potential. The pre-cap value exists only at the moment of the cap check, so recording it there is the only accurate option.

## Consequence for the reported numbers

The potential-based floor has a much smaller CV² (about 0.025 at the reference seed) than the committed series (about 0.9-1.3), because potential generation is a smooth seasonal-plus-noise process while committed generation was lumpy, with dropouts whenever storage saturated. This is the intended result. A low, flat source-variance floor with the Treatment and Collector echelon ratios well above it is the "amplification enters in the middle of the chain" result ADR 0004 predicted. The gap between committed and potential generation (generation dropped to landfill under storage pressure) is itself a reportable property of the supply-driven chain, but it is an *echelon/throughput* observation, not a source-variance one.

## References

- `docs/adr/0004-throughput-bullwhip-measurement.md`: the parent decision. This ADR refines its "source-variance floor (reference, not an echelon)" clause and its claim that "generation CV² is a policy-invariant seasonal baseline", which holds only for potential generation.
- `fransooMeasuringBullwhipEffect2000`: Fransoo & Wouters (2000). The CV²-normalized measure and the aggregation-level concern, carried over unchanged from ADR 0004.
