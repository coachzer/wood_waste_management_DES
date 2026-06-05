# Wood Waste Management DES

Discrete event simulation of wood waste collection, treatment,
and product manufacturing in Slovenia. Models the flow from waste
generation through collection and treatment into final wood-based
products (MDF, particle board, OSB).

## Language

**Demand Envelope**:
The total annual volume of each product type that the market
consumes over a 365-day simulation run. Specified as an annual
total in `demand.json`, consumed continuously via a market
consumption process.
_Avoid_: quota, target, order

**Market Consumption**:
A SimPy process that periodically removes finished products from
treatment operators' finished goods inventory, simulating buyers
taking delivery. Drives the demand signaling rate and keeps
processors active throughout the simulation year.
_Avoid_: sales, shipment

**Service Level**:
The fraction of demand that was fulfilled when consumption
occurred. Two derived metrics from the same consumption-event
log:

- `full_service_level` (headline) =
  `total_consumed / total_attempted` — includes both
  `no_capability` and `stockout` lost sales. Used as the
  cross-policy comparator because the `no_capability` floor is
  identical across all six PUSH/PULL x strategy configurations
  (same regional capability layout).
- `operational_service_level` (diagnostic) =
  `total_consumed / (total_attempted - no_capability_lost)` —
  measures policy effectiveness on demand the system can actually
  fulfill. Strips the structural floor to expose pure operational
  performance.

Per-operator and per-product breakdowns derive from the same
event log by filtering. Only meaningful because demand arrives
continuously — a one-shot quota would yield binary hit/miss.
_Avoid_: fill rate, completion rate,
feasible service level (use `operational_service_level`)

**Treatment Operator**:
A production facility that converts waste into final products. In
PUSH mode, replenishes based on internal inventory thresholds. In
PULL mode, produces in response to **Consumption Events**.
_Avoid_: processor, factory

**Finished Goods**:
A **Treatment Operator**'s buyer-facing inventory of completed
products (MDF, particle board, OSB). Drained by
**Market Consumption**, filled by production. Capacity is
**per product type**:
`finished_goods_capacity[P] = market_share x (annual_demand[P] / 52) x 4`
(four weeks of _that product's_ expected consumption); the
operator's aggregate buffer is their sum. **Initial Inventory**
primes each product at 50% (two weeks). Production is clamped
per output type to that product's remaining headroom — a
saturated OSB buffer throttles OSB transformations even when MDF
has headroom. Replaces the prior two-buffer `product_to_sell` +
`product_storage` design; the secondary buffer had no drain path
and was always vestigial.
_Avoid_: product_to_sell (old name),
inventory (too generic — could mean waste_storage too)

**PUSH (Inventory Policy)**:
Each entity reasons from its own observable state — inventory
levels, storage utilization, reorder points. Information does not
flow downstream-to-upstream as events. The
**Market Consumption** process drains `finished_goods` but does
not notify PUSH operators; they detect the inventory drop via
their **Stock Strategy** thresholds. Physical storage capacity
serves as the implicit production target — there is no separate
forecast or `target_inventory` parameter. PUSH-ON_DEMAND =
produce until full; PUSH-REORDER_50 = produce until 50% of
capacity. Structurally: make-to-stock without explicit forecast.
_Avoid_: forecast-driven, planned

**PULL (Inventory Policy)**:
The trigger is the downstream consumption event itself, not the
inventory drop it causes. When the **Market Consumption** process
pulls from a PULL operator, that operator is woken by the
per-tick **Market Signal** and reads its **Consumption Events**
for the tick, producing each product up to that product's
`attempted` volume, subject to the partial-batch headroom clamp
on `finished_goods`. The **Stock Strategy** gates upstream
waste-side replenishment only: after production consumes input
waste, if `waste_storage` has dropped below the strategy
threshold, the operator signals upstream collectors. Production
responds to every event regardless of `finished_goods` level —
strategy does not target a downstream buffer. The signal chain is
causal: consumption causes production; production causes upstream
waste demand when the strategy threshold is crossed; upstream
waste demand causes collector activity. No autonomous polling on
`finished_goods`. Structurally: lot-for-lot downstream,
`(s, S)` policy upstream.
_Avoid_: reactive, demand-driven (too vague)

**Stock Strategy**:
The local waste-side replenishment policy applied at each entity.
Three variants:

- `ON_DEMAND`: signal upstream lot-for-lot — every waste
  consumption triggers a signal for replacement volume
- `REORDER_50`: signal upstream when `waste_storage` drops below
  50% of `waste_storage_capacity`
- `REORDER_90`: signal upstream when `waste_storage` drops below
  90% of capacity

Strategy gates waste-side decisions only (when upstream signals
fire). Does not gate `finished_goods` production: in **PUSH**,
production triggers on autonomous waste-state polling against the
same threshold; in **PULL**, production triggers on
**Consumption Event** arrival regardless of strategy. The
strategy parameter sets the reorder point (`s` in `(s, S)`
notation). The order-up-to level is
`S = waste_storage_capacity` — when threshold breached, the
signal volume is
`waste_storage_capacity - current_waste_storage` (order up to
full capacity). ON_DEMAND under this rule is lot-for-lot:
s = S = capacity, signal_volume = amount-just-consumed.
_Avoid_: reorder policy (overloaded),
inventory policy (that's PUSH/PULL)

**Consumption Event**:
The record of a single market consumption attempt against one
**Treatment Operator** for one product, written to the
consumption-event log on `SimulationState`. Carries product type,
`attempted` volume (full demand including any unfulfilled
portion), `consumed`, and the **Lost Sales** reason. The log is
the authoritative per-product record and the basis for
**Service Level**.

A PULL operator is _notified_ that consumption occurred by a
single per-tick **Market Signal** (delivered via
**KanbanManager**, `source_type="market"`) carrying its total
producible `attempted` volume — an edge trigger, not the payload.
On that trigger the operator reads its Consumption Events for the
tick from the log and sets each product's production target to
that product's `attempted`, so a stockout on tick N does not
silence production on tick N+1 (no death-spiral). Lost-sale
tracking stays at the `SimulationState` level; the operator never
needs `consumed` or `lost`. The aggregate Market Signal keeps the
PULL cascade uniform (market -> treatment -> collector ->
generator) while per-product demand comes from the log.
_Avoid_: demand signal, order

**Market Signal**:
The per-tick, per-operator edge trigger emitted by
**Market Consumption** to a PULL **Treatment Operator** (via
**KanbanManager**, `source_type="market"`), carrying the
operator's total producible `attempted` volume for that
**Consumption Tick**. It wakes the operator and is acknowledged
once; the per-product production targets come from the
**Consumption Event** log, not from this signal. Distinct from a
**Demand Signal**, which is the operator's downstream waste-side
request to collectors.
_Avoid_: consumption signal, market order

**Demand Signal**:
A request from a **Treatment Operator** to collectors (and
transitively to generators) for a specific waste type and volume.
In PULL mode, triggered by **Consumption Events**. In PUSH mode,
triggered by stock strategy thresholds detecting low inventory.
_Avoid_: order, request

**Throughput Bullwhip**:
The variance amplification of _physical replenishment flow_
relative to market demand, measured per ordering echelon as the
cross-policy PUSH-vs-PULL evidence. Defined on
**delivered flow**, not on **Demand Signals** — those are not
observable in PUSH (collectors ignore generator signals) and are
not persisted, so flow is the only quantity logged identically
under both policies. _Delivered flow_ is the physical
replenishment that actually enters the receiving echelon: for
Treatment that is collector `provide_waste_for_treatment` intake,
NOT the cross-region `collector->collector` repositioning the
transport-flow log originally mislabeled `collector->treatment`
(ADR 0009). Normalized as a squared coefficient of variation
ratio,
`CV^2(echelon weekly inbound flow) / CV^2(weekly market consumption)`,
so the value is unit-free across the waste-to-product commodity
change and `> 1` means amplification. There are **two ordering
echelons** — Treatment (`collector->treatment` flow, the intake)
and Collector (`generator->collector` flow); waste
**generation** is an exogenous _source-variance floor_, not a
third echelon, because generators do not order. The
transport-flow log carries a third link,
`collector->collector` (cross-region repositioning between
collection centers), which is an intra-Collector-echelon move,
not an ordering echelon, so no bullwhip echelon reads it
(ADR 0009). This is a doubly-exogenous chain — both market
consumption and waste generation are exogenous — so amplification
is injected in the middle, not grown toward the source. The
denominator anchor is consumption `attempted` (the exogenous
demand presented), never `consumed` (already shaped by
stockouts). The source floor is measured on
**potential generation** (the volume the source process offers
each tick, pre storage cap), not **committed generation**
(`total_generated`, what actually entered storage): committed
generation is capped by storage headroom, which finite-storage
backpressure couples to policy, so its CV^2 carries a policy
signal (it swings ~0.9-1.3 across the six combos) while the
potential-based floor is policy-invariant (byte-identical across
combos). Beside the two anchored _headline_ ratios sits a
**stage-by-stage diagnostic** (`treatment_stage`,
`collector_stage`) that localizes _where_ amplification enters:
Treatment stage =
`CV^2(treatment inbound)/CV^2(consumption)`, Collector stage =
`CV^2(collector inbound)/CV^2(treatment inbound)`. The stages
are computed on the **system-pooled** per-echelon series (every
node summed before CV^2), not the per-node volume-weighted
aggregation the headline uses — that is the only level at which
they telescope exactly to the anchored ratio
(`treatment_stage x collector_stage = pooled collector anchored`),
because a product of per-node weighted averages is not the
weighted average of products. So `treatment_stage` is the
_pooled_ Treatment ratio, which sits below the per-node
`treatment_anchored` headline (pooling smooths out-of-phase
spikes). The same pooled per-echelon series also backs a
**pooled robustness variant** (`treatment_anchored_pooled`,
`collector_anchored_pooled`): the anchored ratios recomputed
pooled rather than per-node-volume-weighted, a conservative lower
bound on the headline — if pooled still shows PUSH > PULL the
result is strong. `treatment_anchored_pooled` equals
`treatment_stage` by construction (same pooled-treatment CV^2
over consumption), and `collector_anchored_pooled` equals the
telescoped product `treatment_stage x collector_stage`; both
keys are emitted anyway so the robustness pair reads in parallel
beside the headline pair. Method and rationale: ADR 0004, refined
by ADR 0005 (floor), ADR 0006 (stage telescoping aggregation
level), ADR 0007 (pooled variant emits both echelon keys despite
the Treatment identity), and ADR 0009 (Treatment inbound is
collector intake, not the transport-log repositioning).
_Avoid_: order bullwhip (the metric is flow-based, not
order-based), bullwhip ratio (unqualified — say which echelon
and that it is CV^2-normalized), generation floor on
committed/`total_generated` (the floor is on potential
generation — committed carries a policy signal)

**Seasonal Pattern**:
A sinusoidal factor `1 + 0.2 * sin(2*pi*t/T)` applied to both
waste generation rates and market consumption rates. Peaks in
summer (more construction activity), troughs in winter. Shared
between generators and consumption so that supply and demand are
driven by the same underlying seasonality.
_Avoid_: seasonal index
(ambiguous — could refer to the array index or the factor value)

**Consumption Tick**:
The weekly interval (every 7 time units) at which the
**Market Consumption** process removes products from treatment
operators' finished goods inventory. Each tick consumes
`(annual_demand / 52) * seasonal_factor` per product type,
distributed across operators.
_Avoid_: consumption rate, sales cycle

**Lost Sales**:
When a **Consumption Tick** cannot be fully fulfilled from
available finished goods inventory, the unfulfilled portion is
lost — the market sourced from a competitor. The shortfall counts
against **Service Level**. No backlog carries over to the next
tick. Each lost sale is tagged by reason: `no_capability`
(operator has no transformation pathway for the requested
product) or `stockout` (operator could produce it but had
insufficient stock). Per-operator service level reports both
components separately; system-level service level aggregates
them.
_Avoid_: stockout
(as a general term — use the specific reason tags)

**Consumption Distribution**:
Each **Treatment Operator**'s share of weekly
**Market Consumption** is proportional to its processing capacity
relative to the national total. A facility with 64,000 m^3
capacity absorbs more consumption than one with 14,400 m^3. Each
facility has its own effective regional market share.
_Avoid_: market allocation, demand split

**ABC Classification**:
A Pareto-style prioritization of output products (OSB, particle
board, MDF) by total biogenic carbon stock impact. Products are
ranked by `demand_volume x biogenic_carbon_per_unit`, then
classified: Class A (cumulative <=70%, weight 1.0), Class B
(<=95%, weight 0.7), Class C (remainder, weight 0.4). Current
classification: OSB = A, particle board = B, MDF = C. The
priority weights feed into transformation selection scoring at a
2.0x multiplier, making ABC the dominant factor in what a
**Treatment Operator** produces when multiple transformations are
available. Always enabled — every processor runs with the same
classification. Not traditional Activity-Based Costing; this is
an environmental-impact Pareto ranking.
_Avoid_: Activity-Based Costing, cost classification

**Run**:
One invocation of `main.py` — the entire batch of simulations it
produces. A grid run executes one simulation per policy/strategy
combo; a baseline run executes N replications per combo.
Individual simulations within a baseline run are replications,
not runs. Runs are identified by a generated name encoding mode,
variant, and flags, and all artifacts (config snapshot, results,
plots, per-replication data) live in a single run directory.
_Avoid_: experiment, trial, execution

**Run Name**:
An auto-generated slug that identifies a run at a glance:
`{mode}_{variant}_{flags}__{HHMM}`. Mode is the execution shape
(`grid`, `baseline`). Variant is the scenario filter, present
only when `--scenario` restricts to one (omitted when running all
scenarios). Flags are non-default parameters (`n50` for 50
replications). The `__HHMM` suffix disambiguates same-config runs
on the same day.
_Avoid_: run ID, job name

**Initial Inventory**:
All echelons are primed with 2 weeks of inventory at expected
consumption rate before simulation starts. Treatment operators'
`finished_goods` is initialized to
`(annual_demand / 52) * 2 * market_share` per product type — 50%
of `finished_goods_capacity` (which is sized for four weeks),
giving symmetric headroom for over- and under-production phases.
Waste storage is initialized to enough waste to produce 2 weeks
of product (the 2-week product target divided by blended
transformation efficiency), distributed across the operator's
input waste types in proportion to the region's waste generation
mix. Collectors and generators use existing `initial_stock` from
region JSON. Same initial conditions for both PUSH and PULL —
ensures fair comparison and avoids cold-start artifacts in
early-simulation metrics.
_Avoid_: warm-up stock, safety stock (different concept)

**Avoided Emissions**:
The greenhouse-gas emissions the system avoids by displacing
**virgin-feedstock production** of the same wood-based product.
Because every MDF / particle board / OSB unit is made from
recovered wood waste, it stands in for a functionally identical
panel that would otherwise have been manufactured from primary
(virgin) wood — and that virgin production's footprint is
avoided. Driven by recycled **produced volume** per product type,
scaled by a per-product literature factor. A
_recycling avoided-burden_ (secondary vs primary production of
the same good), **not** a material-substitution claim — the model
does not represent the buyer choosing wood over
concrete/steel/plastic, so no non-wood displacement is asserted.
Reported as a benefit alongside, and on a different system
boundary from, the operational emissions in
`total_emissions_kgco2e`.
_Avoid_: substitution effect (implies non-wood material
displacement), displacement factor (that is the per-carbon-mass
material-substitution metric, a different concept), carbon credit

**Biogenic Carbon Stored**:
The biogenic carbon locked into the panels the system produces,
reported as a static, production-weighted credit:
`Σ_product (produced_volume_p × biogenic_carbon_stock_p)`, summed
across **Treatment Operators**, where the per-m³ stock lives on
`ProductSpecification.biogenic_carbon_stock`
(`models/products.py`). Sign convention is **negative =
sequestered** (carbon held out of the atmosphere), so the credit
reads negative beside the positive operational
`total_emissions_kgco2e`. It is the **static** stock view, _not_
the time-integrated / dynamic GWP-bio (Levasseur) view — that
needs a product service-life and end-of-life release profile the
model does not have (it stops at **Market Consumption**), so it
is named as future work, not computed. One of three orthogonal
carbon lines reported **side by side, never netted** (ADR 0011):
biogenic-stored (this), **Avoided Emissions**, and operational
`total_emissions_kgco2e`. Orthogonality is binding — biogenic
carbon is excluded from `total_emissions_kgco2e`, and the
avoided-emissions factors are biogenic-excluded too — so the
three never double-count.
_Avoid_: GWP-bio / dynamic-LCA (this is the static stock, not the
time-integrated view), carbon sequestration credit (overclaims a
permanence the single-cycle model does not assert), net carbon
(the lines are not netted)

**Cascading Depth**:
The number of successive use-cycles a material passes through
before final disposal. In this model it is **1**: each unit of
wood waste is transformed exactly once — by a
**Treatment Operator** into a finished good (MDF / particle board
/ OSB) that leaves the system boundary at **Market Consumption**.
There is no path that returns a manufactured product to the waste
stream for re-treatment, so the mass ledgers close on a single
waste-to-product cycle. Multi-cycle cascading — product reuse, a
recovered panel re-entering as feedstock, sequential
down-gauging across product grades — is named as **future work**,
not modelled. Reported as a documented modelling assumption
(depth = 1), deliberately **not** as a per-run KPI: a constant
carries no Monte-Carlo or paired-statistics signal, so surfacing
it as a column of `1.0`s would be hollow plumbing. The honest
deliverable is the stated assumption, which pre-empts the
reviewer question "did you consider cascading reuse?".
_Avoid_: reuse count, recycling loops (plural — there is one
cycle), number of lifecycles (the model has no product use phase)

## Example dialogue

> **Dev**: "The simulation finishes at day 100 — all demands
> are met."
> **Domain expert**: "That's wrong. The demand envelope is
> 30,000 m^3 of OSB _per year_. The market consumes that over
> 365 days. If processors produce faster than the market
> consumes, product piles up in finished goods inventory — it
> doesn't mean demand is 'met.' Service level measures whether
> we keep up with consumption, not whether we hit a ceiling."
