# Bullwhip measured as a CV²-normalized throughput-flow ratio, not order variance

> Partially superseded by ADR 0009: the Treatment-echelon inbound flow is collector `provide_waste_for_treatment`
> intake, NOT the `collector -> treatment` entries in `transport_flows` (those are cross-region repositioning).
> The rest of this decision — CV² normalization, consumption-`attempted` anchor, two echelons, warm-up,
> per-node-then-weighted aggregation — stands. Body left as written (append-only).

The metrics roadmap (P2) calls for bullwhip quantification — `var(orders)/var(consumption)` per echelon — as the core PUSH-vs-PULL evidence. ADR 0002 already predicts the qualitative result (PULL-ON_DEMAND approaches the unit lower bound, REORDER_X amplifies via lot-sizing). This ADR fixes *how the number is actually computed*, because the textbook formula does not survive contact with this model: orders are not observable in PUSH, the commodity changes units mid-chain, and one of the three nominal echelons does not place orders at all. Every choice below was made to keep the metric well-defined and comparable across all six PUSH/PULL × strategy configurations.

## Decision

For each ordering echelon, the throughput bullwhip is

```
BW_echelon = CV²(weekly inbound replenishment flow) / CV²(weekly market consumption)
           = [Var(flow)/mean(flow)²] / [Var(consumption)/mean(consumption)²]
```

computed per node over weeks 5–52 of a single run, then **volume-weighted averaged across the nodes of the echelon**, then averaged across Monte-Carlo replications with CRN-paired PUSH-vs-PULL differences. `BW > 1` is amplification; `BW = 1` is clean pass-through.

Reported figures:

- **Anchored headline (2 values):** Treatment and Collector echelons, each anchored to the *same* market-consumption CV². This is the cumulative amplification from the exogenous demand.
- **Stage-by-stage diagnostic:** Treatment stage = `CV²(treatment inbound)/CV²(consumption)`; Collector stage = `CV²(collector inbound)/CV²(treatment inbound)`. The stage ratios telescope to the anchored values and localize *where* amplification is injected (expected: the REORDER (s,S) step).
- **Source-variance floor (reference, not an echelon):** `CV²(weekly waste generation)`, reported to show the upstream source is policy-invariant.
- **Pooled robustness check:** the same anchored ratios computed on a system-pooled weekly series (all nodes summed before CV²), expected to *understate* the per-node number — if pooled still shows PUSH > PULL, the result is strong.

## Why these choices (the rejected alternatives)

- **Flow, not orders.** **Demand Signals** are the literal "orders," but in PUSH collectors ignore generator signals (collection is volume-driven) and signals are never persisted (`KanbanManager.signal_history` is dead; live signals are acknowledged-and-dropped at 24h). The only quantity logged identically under both policies is physical delivered flow from `SimulationState.transport_flows`. Rejected: (a) logging signals and using true order variance — still undefined for PUSH, so it cannot be the cross-policy comparator, defeating the purpose; (b) a hybrid (orders in PULL, flow in PUSH) — makes the numerator mean different things on each side of the comparison. The honest consequence: this is a *throughput/shipment* bullwhip, named accordingly, and the absence of an observable order signal in PUSH is itself a reportable structural finding.

- **CV²-normalized, not raw `var/var`.** The commodity changes at treatment: consumption is in product m³ (MDF/PB/OSB), every upstream flow is in waste m³. Raw `Var(waste)/Var(product)` divides incommensurable units and scales with transformation efficiency rather than amplification. The squared-CV ratio (Fransoo & Wouters 2000, the operational companion to Chen et al.) normalizes each series by its own mean, is unit-free across the commodity change, and additionally neutralizes the asymmetric absolute volumes of 12 regions. Same interpretation (`>1` = amplification), robust to the unit change.

- **Two ordering echelons, not three.** This is a doubly-exogenous chain: market consumption pulls downstream *and* waste generation pushes upstream at a fixed seasonal rate. Generators do not order — their generation CV² is a policy-invariant seasonal baseline. Forcing a "generator echelon" (generation series) yields a ratio that never moves across policies and invites the question "why is it dead?"; collapsing it onto the `generator→collector` link double-counts the collector's series. So generation is reported as a *source-variance floor* reference, and the two real ordering echelons (Treatment, Collector) carry the PUSH-vs-PULL signal. Consequence worth stating in the paper: amplification here is injected in the *middle* of the chain, the inverse of the textbook upstream-growing picture — a property of circular/supply-driven chains.

- **Anchor on `attempted`, not `consumed`.** The denominator is weekly total consumption `attempted` (the exogenous demand presented to operators). `consumed` is endogenous — already depressed by stockouts — and using it would let the system's own failure to fulfill demand deflate the reference variance.

- **Per-node CV² then volume-weighted average; pooled only as a check.** Pooling node series before CV² smooths exactly the lumpy, out-of-phase (s,S) reorder spikes that *are* the PUSH bullwhip signal, systematically understating the PUSH penalty. Per-node-first preserves the mechanism; volume-weighting stops a tiny-flow node (CV² explodes as mean→0) from dominating. Pooled is kept as a conservative lower-bound robustness check.

- **Total volume per node.** Per-(node, waste-type) series inject waste-type *substitution churn* as spurious variance (an operator swapping input types at steady total inflow is not bullwhip) and need an arbitrary cross-type reweighting. Total weekly volume per node is consistent with the aggregated consumption anchor. Per-type and per-product decompositions are deferred to bucket-C MFA depth.

- **Weekly bins, drop first 4 weeks, no deseasonalizing.** The **Consumption Tick** is weekly, giving ~52 native bins — a stable variance estimate (monthly's 12 bins would not be). The first 4 weeks are the **Initial Inventory** cold-start ramp (2-week prime, 4-week buffer sizing) and inflate variance asymmetrically across policies; they are dropped (warm-up length is a named constant in `config/constants.py`, not a magic number). The **Seasonal Pattern** injects real variance into *both* numerator and denominator, which the CV² ratio correctly attributes to neither under clean pass-through — bullwhip is the *excess* over seasonal transmission, so deseasonalizing would discard the one demand signal that should propagate. End-of-year weeks are kept, with a check that trimming the last 1–2 weeks does not move the result.

## Reconciliation with ADR 0002

ADR 0002 frames the treatment-echelon bullwhip as `var(production_orders) = var(attempted_demand)` → unit ratio for PULL-ON_DEMAND. That is an **order-based, downstream-facing** claim about the *production* response. This metric is **flow-based, upstream-facing** (inbound waste vs demand) and uniform across both ordering echelons so they are comparable. The two are complementary, not the same number; ADR 0002's production-order prediction can be cited as a separate analytical lower-bound, but the reported echelon metric is the flow ratio defined here.

## References

- `chenQuantifyingBullwhipEffect2000` — Chen, Drezner, Ryan & Simchi-Levi (2000), *Management Science* 46(3):436-443. The canonical order-variance bullwhip derivation and lower-bound framing.
- `fransooMeasuringBullwhipEffect2000` — Fransoo & Wouters (2000), *Supply Chain Management* 5(2):78-89. The CV²-normalized operational measure implemented here; also the source of the aggregation-level (per-node vs pooled) measurement concern that motivates the per-node-primary / pooled-robustness split.

Supporting / related (situate the result, not the formula):

- `ponteQuantifyingBullwhipClosedLoop2020` — Ponte et al. (2020), *Int. J. Production Economics* 230. Order/inventory variance amplification in closed-loop supply chains; the closest published analogue to this model's circular, doubly-exogenous structure.
- `isakssonQuantifyingBullwhipTwoEchelon2016` — Isaksson & Seifert (2016), *Int. J. Production Economics* 171:311-320. Cross-industry empirical bullwhip (≈1.90 between echelons); a real-world magnitude anchor for the Discussion.

All four are in `paper-draft/latex/references.bib`.
