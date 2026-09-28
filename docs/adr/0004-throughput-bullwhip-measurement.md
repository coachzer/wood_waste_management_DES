# Bullwhip measured as a CV²-normalized throughput-flow ratio, not order variance

> Partially superseded by ADR 0009. The Treatment-echelon inbound flow is collector `provide_waste_for_treatment`
> intake, NOT the `collector -> treatment` entries in `transport_flows` (those are cross-region repositioning).
> The rest of this decision stands: CV² normalization, the consumption-`attempted` anchor, two echelons,
> warm-up, and per-node-then-weighted aggregation. The body keeps its original meaning (append-only).

The metrics roadmap (P2) calls for bullwhip quantification, `var(orders)/var(consumption)` per echelon, as the core PUSH-vs-PULL evidence. ADR 0002 already predicts the qualitative result: PULL-ON_DEMAND approaches the unit lower bound, and REORDER_X amplifies through lot sizing. This ADR fixes *how the number is computed*, because the textbook formula does not fit this model. Orders are not observable in PUSH, the commodity changes units mid-chain, and one of the three nominal echelons places no orders. Every choice below keeps the metric well-defined and comparable across all six PUSH/PULL × strategy configurations.

## Decision

For each ordering echelon, the throughput bullwhip is

```
BW_echelon = CV²(weekly inbound replenishment flow) / CV²(weekly market consumption)
           = [Var(flow)/mean(flow)²] / [Var(consumption)/mean(consumption)²]
```

It is computed per node over weeks 5-52 of a single run, then **volume-weighted averaged across the nodes of the echelon**, then averaged across Monte Carlo replications with CRN-paired PUSH-vs-PULL differences. `BW > 1` is amplification and `BW = 1` is clean pass-through.

Reported figures:

- **Anchored headline (2 values).** Treatment and Collector echelons, each anchored to the *same* market-consumption CV². This is the cumulative amplification from the exogenous demand.
- **Stage-by-stage diagnostic.** Treatment stage = `CV²(treatment inbound)/CV²(consumption)`. Collector stage = `CV²(collector inbound)/CV²(treatment inbound)`. The stage ratios telescope to the anchored values and show *where* amplification enters (expected: the REORDER (s,S) step).
- **Source-variance floor (reference, not an echelon).** `CV²(weekly waste generation)`, reported to show that the upstream source is policy-invariant.
- **Pooled robustness check.** The same anchored ratios computed on a system-pooled weekly series (all nodes summed before CV²). It is expected to *understate* the per-node number, so if pooled still shows PUSH > PULL, the result is strong.

## Why these choices (the rejected alternatives)

- **Flow, not orders.** **Demand Signals** are the literal "orders", but in PUSH collectors ignore generator signals (collection is volume-driven), and signals are never persisted (`KanbanManager.signal_history` is dead, and live signals are acknowledged and dropped at 24h). The only quantity logged the same way under both policies is physical delivered flow from `SimulationState.transport_flows`. Rejected: (a) logging signals and using true order variance, which is still undefined for PUSH and so cannot be the cross-policy comparator; (b) a hybrid (orders in PULL, flow in PUSH), which makes the numerator mean different things on each side of the comparison. As a consequence, this is a *throughput/shipment* bullwhip and is named that way. The lack of an observable order signal in PUSH is itself a reportable structural finding.

- **CV²-normalized, not raw `var/var`.** The commodity changes at treatment. Consumption is in product m³ (MDF/PB/OSB), and every upstream flow is in waste m³. Raw `Var(waste)/Var(product)` divides incommensurable units and scales with transformation efficiency instead of amplification. The squared-CV ratio (Fransoo & Wouters 2000, the operational companion to Chen et al.) normalizes each series by its own mean. It is unit-free across the commodity change and also neutralizes the unequal absolute volumes of the 12 regions. The interpretation is the same (`>1` = amplification), and it holds up under the unit change.

- **Two ordering echelons, not three.** This is a doubly exogenous chain. Market consumption pulls downstream *and* waste generation pushes upstream at a fixed seasonal rate. Generators do not order, so their generation CV² is a policy-invariant seasonal baseline. A forced "generator echelon" (generation series) gives a ratio that never moves across policies and invites the question "why is it dead?". Mapping it onto the `generator→collector` link double-counts the collector's series. So generation is reported as a *source-variance floor* reference, and the two real ordering echelons (Treatment, Collector) carry the PUSH-vs-PULL signal. A consequence worth stating in the paper: amplification here enters in the *middle* of the chain, the inverse of the textbook picture where it grows upstream. This is a property of circular, supply-driven chains.

- **Anchor on `attempted`, not `consumed`.** The denominator is weekly total consumption `attempted`, the exogenous demand presented to operators. `consumed` is endogenous, already lowered by stockouts, and using it would let the system's own failure to fulfill demand shrink the reference variance.

- **Per-node CV² then volume-weighted average, with pooled only as a check.** Pooling node series before CV² smooths out the lumpy, out-of-phase (s,S) reorder spikes that *are* the PUSH bullwhip signal, which systematically understates the PUSH penalty. Computing per node first preserves the mechanism. Volume weighting stops a tiny-flow node (whose CV² explodes as mean→0) from dominating. Pooled is kept as a conservative lower-bound robustness check.

- **Total volume per node.** Per-(node, waste-type) series add waste-type *substitution churn* as spurious variance (an operator swapping input types at a steady total inflow is not bullwhip), and they need an arbitrary cross-type reweighting. Total weekly volume per node is consistent with the aggregated consumption anchor. Per-type and per-product decompositions are deferred to bucket-C MFA depth.

- **Weekly bins, drop the first 4 weeks, no deseasonalizing.** The **Consumption Tick** is weekly, which gives about 52 native bins and a stable variance estimate (monthly binning's 12 bins would not). The first 4 weeks are the **Initial Inventory** cold-start ramp (2-week prime, 4-week buffer sizing), which inflates variance unevenly across policies, so they are dropped. The warm-up length is a named constant in `config/constants.py`. The **Seasonal Pattern** adds real variance to *both* numerator and denominator, and under clean pass-through the CV² ratio correctly attributes it to neither. Bullwhip is the *excess* over seasonal transmission, so deseasonalizing would discard the one demand signal that should propagate. End-of-year weeks are kept, with a check that trimming the last 1-2 weeks does not move the result.

## Reconciliation with ADR 0002

ADR 0002 frames the treatment-echelon bullwhip as `var(production_orders) = var(attempted_demand)`, a unit ratio for PULL-ON_DEMAND. That is an **order-based, downstream-facing** claim about the *production* response. This metric is **flow-based and upstream-facing** (inbound waste vs demand), and it is defined the same way for both ordering echelons so they are comparable. The two are complementary, not the same number. ADR 0002's production-order prediction can be cited as a separate analytical lower bound, but the reported echelon metric is the flow ratio defined here.

## References

- `chenQuantifyingBullwhipEffect2000`: Chen, Drezner, Ryan & Simchi-Levi (2000), *Management Science* 46(3):436-443. The canonical order-variance bullwhip derivation and lower-bound framing.
- `fransooMeasuringBullwhipEffect2000`: Fransoo & Wouters (2000), *Supply Chain Management* 5(2):78-89. The CV²-normalized operational measure implemented here. It is also the source of the aggregation-level (per-node vs pooled) measurement concern behind the per-node-primary, pooled-robustness split.

Supporting and related work (places the result in context, not the formula):

- `ponteQuantifyingBullwhipClosedLoop2020`: Ponte et al. (2020), *Int. J. Production Economics* 230. Order and inventory variance amplification in closed-loop supply chains. The closest published analogue to this model's circular, doubly exogenous structure.
- `isakssonQuantifyingBullwhipTwoEchelon2016`: Isaksson & Seifert (2016), *Int. J. Production Economics* 171:311-320. Cross-industry empirical bullwhip (about 1.90 between echelons), a real-world magnitude anchor for the Discussion.

All four are in `paper-draft/latex/references.bib`.
