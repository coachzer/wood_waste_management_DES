# Wood Waste Management DES

Discrete event simulation of wood waste collection, treatment,
and product manufacturing in Slovenia. Models the flow from waste
generation through collection and treatment into final wood-based
products (MDF, particle board, OSB).

## Language

**Demand Envelope**:
The total annual volume of each product type that the market
consumes over a 365-day simulation run. `demand.json` gives it as
an annual total, and a market consumption process draws it down
continuously.
_Avoid_: quota, target, order

**Market Consumption**:
A SimPy process that periodically removes finished products from
treatment operators' finished goods inventory, simulating buyers
taking delivery. It sets the demand signaling rate and keeps
processors active through the simulation year.
_Avoid_: sales, shipment

**Service Level**:
The fraction of demand fulfilled when consumption occurred. Two
metrics derive from the same consumption-event log:

- `full_service_level` (headline) =
  `total_consumed / total_attempted`. It includes both
  `no_capability` and `stockout` lost sales. It is the
  cross-policy comparator because the `no_capability` floor is
  identical across all six PUSH/PULL x strategy configurations
  (same regional capability layout).
- `operational_service_level` (diagnostic) =
  `total_consumed / (total_attempted - no_capability_lost)`. It
  measures policy performance on demand the system can actually
  fulfill, with the structural floor removed.

Per-operator and per-product breakdowns filter the same event
log. The metric only means something because demand arrives
continuously. A one-shot quota would yield a binary hit or miss.
_Avoid_: fill rate, completion rate,
feasible service level (use `operational_service_level`)

**Treatment Operator**:
A production facility that converts waste into final products. In
PUSH mode, it replenishes based on internal inventory thresholds.
In PULL mode, it produces in response to **Consumption Events**.
_Avoid_: processor, factory

**Finished Goods**:
A **Treatment Operator**'s buyer-facing inventory of completed
products (MDF, particle board, OSB). **Market Consumption** drains
it and production fills it. Capacity is **per product type**:
`finished_goods_capacity[P] = market_share x (annual_demand[P] / 52) x 4`
(four weeks of _that product's_ expected consumption). The
operator's aggregate buffer is their sum. **Initial Inventory**
starts each product at 50% (two weeks). Production is clamped per
output type to that product's remaining headroom, so a full OSB
buffer throttles OSB transformations even when MDF has headroom.
_Avoid_: product_to_sell (old name),
inventory (too generic, could mean waste_storage too)

**PUSH (Inventory Policy)**:
Each entity decides from its own observable state: inventory
levels, storage utilization, reorder points. Information does not
flow downstream-to-upstream as events. The **Market Consumption**
process drains `finished_goods` but does not notify PUSH
operators. They detect the inventory drop through their
**Stock Strategy** thresholds. Physical storage capacity is the
implicit production target. There is no separate forecast or
`target_inventory` parameter. PUSH-ON_DEMAND produces until full.
PUSH-REORDER_50 produces until 50% of capacity. Structurally this
is make-to-stock without an explicit forecast.
_Avoid_: forecast-driven, planned

**PULL (Inventory Policy)**:
The trigger is the downstream consumption event itself, not the
inventory drop it causes. When **Market Consumption** pulls from a
PULL operator, the per-tick **Market Signal** wakes that operator.
The operator reads its **Consumption Events** for the tick and
produces each product up to that product's `attempted` volume,
subject to the partial-batch headroom clamp on `finished_goods`.
The **Stock Strategy** gates upstream waste-side replenishment
only. After production consumes input waste, if `waste_storage`
has dropped below the strategy threshold, the operator signals
upstream collectors. Production responds to every event whatever
the `finished_goods` level. Strategy does not target a downstream
buffer. The signal chain is causal. Consumption causes
production. Production causes upstream waste demand when the
strategy threshold is crossed. Upstream waste demand causes
collector activity, but only while the collector's collection
center is below the collector utilization ceiling (ADR 0022).
A PULL generator never calls for pickup on its own stock, however
full it is (ADR 0032), so only waste some operator ordered moves.
A collector serves treatment orders first, largest first, and only
the newest order per operator and waste type (ADR 0031).
A PULL collector with no signal does not collect at all, however
empty its collection center is (ADR 0025).
No process polls `finished_goods` on its own.
Structurally this is lot-for-lot downstream and an `(s, S)`
policy upstream.
_Avoid_: reactive, demand-driven (too vague)

**Stock Strategy**:
The local waste-side replenishment policy applied at each entity.
Three variants:

- `ON_DEMAND`: signal upstream lot-for-lot. Every waste
  consumption triggers a signal for the replacement volume.
- `REORDER_50`: signal upstream when a waste type's stock drops
  below 50% of its order-up-to level.
- `REORDER_90`: signal upstream when a waste type's stock drops
  below 90% of its order-up-to level.

Strategy gates waste-side decisions only, meaning when upstream
signals fire. It does not gate `finished_goods` production. In
**PUSH**, production triggers on periodic polling of the
operator's own waste state against the same threshold. In
**PULL**, production triggers when a **Consumption Event**
arrives, whatever the strategy. Treatment runs one `(s, S)` per input waste type
(ADR 0026). The order-up-to level `S` is sized from demand, not
storage capacity: one consumption interval of waste need plus
`z = 1.645` seasonal standard deviations, the same for PUSH and
PULL (ADR 0027). Each type's level is its share of `S`, from
product need and the national generation mix. The strategy sets
the reorder point as a fraction of that level: ON_DEMAND `s = S`,
REORDER_50 `s = 0.5 S`, REORDER_90 `s = 0.9 S`. When a type is
below its `s`, it orders the gap to its level, so ON_DEMAND is
lot-for-lot: it orders back what was consumed. Inventory position
is on-hand stock. This equals the classical position when the local
center holds the type (typically PUSH), because treatment drains
collectors within the tick. Generator and collector thresholds still use storage
capacity.
_Avoid_: reorder policy (overloaded),
inventory policy (that's PUSH/PULL)

**Consumption Event**:
The record of a single market consumption attempt against one
**Treatment Operator** for one product, written to the
consumption-event log on `SimulationState`. It carries the
product type, the `attempted` volume (full demand including any
unfulfilled portion), `consumed`, and the **Lost Sales** reason.
The log is the authoritative per-product record and the basis for
**Service Level**.

A single per-tick **Market Signal** notifies a PULL operator that
consumption occurred. **KanbanManager** delivers it with
`source_type="market"`, and it carries the operator's total
producible `attempted` volume. It is an edge trigger, not the
payload. On that trigger the operator reads its Consumption
Events for the tick from the log and sets each product's
production target to that product's `attempted`. A stockout on
tick N therefore does not silence production on tick N+1, so
there is no death spiral. Lost-sale tracking stays at the
`SimulationState` level, and the operator never needs `consumed`
or `lost`. The aggregate Market Signal keeps the PULL cascade
uniform (market -> treatment -> collector -> generator), while
per-product demand comes from the log.
_Avoid_: demand signal, order

**Market Signal**:
The per-tick, per-operator edge trigger that
**Market Consumption** sends to a PULL **Treatment Operator**
through **KanbanManager** (`source_type="market"`). It carries the
operator's total producible `attempted` volume for that
**Consumption Tick**. It wakes the operator and is acknowledged
once. The per-product production targets come from the
**Consumption Event** log, not from this signal. It differs from
a **Demand Signal**, which is the operator's downstream waste-side
request to collectors.
_Avoid_: consumption signal, market order

**PULL Production Backlog**:
A PULL **Treatment Operator**'s per-product volume still to
produce. It starts at **Finished Goods** capacity minus initial
stock. Each **Market Signal** adds the `consumed` of the tick's
**Consumption Events** for that operator, so finished goods plus
backlog stays at capacity: base-stock with lost sales, up to the
level PUSH produces up to (ADR 0029). Each daily operating tick produces against it,
limited by processing capacity, waste on hand and the
**Finished Goods** headroom clamp, and draws it down by what was
made. Unmet volume carries forward with no expiry, because one
day's capacity cannot cover a week's demand. The backlog still
grows while the operator is FAILED. It is internal production
state only. It never creates a **Consumption Event**, never
changes `attempted`, and plays no part in **Lost Sales** or
**Service Level**, which stay defined at the market (ADR 0020).
_Avoid_: backorder (a Lost Sale does not come back to the market),
order book

**Demand Signal**:
A request from a **Treatment Operator** to collectors (and through
them to generators) for a specific waste type and volume. In PULL
mode, **Consumption Events** trigger it. In PUSH mode, stock
strategy thresholds that detect low inventory trigger it.
_Avoid_: order, request

**Throughput Bullwhip**:
The variance amplification of _physical replenishment flow_
relative to market demand, measured per ordering echelon as the
cross-policy PUSH-vs-PULL evidence. It is defined on
**delivered flow**, not on **Demand Signals**. Demand Signals are
not observable in PUSH (collectors ignore generator signals) and
are not persisted, so flow is the only quantity logged the same
way under both policies.

_Delivered flow_ is the physical replenishment that actually
enters the receiving echelon. For Treatment that is collector
`provide_waste_for_treatment` intake. It is NOT the cross-region
`collector->collector` repositioning that the transport-flow log
originally mislabeled `collector->treatment` (ADR 0009).

The metric is normalized as a squared coefficient of variation
ratio,
`CV^2(echelon weekly inbound flow) / CV^2(weekly market consumption)`,
so the value is unit-free across the waste-to-product commodity
change, and `> 1` means amplification.

There are **two ordering echelons**. Treatment reads the
`collector->treatment` flow (its intake). Collector reads the
`generator->collector` flow. Waste **generation** is an exogenous
_source-variance floor_, not a third echelon, because generators
do not order. The transport-flow log carries a third link,
`collector->collector` (cross-region repositioning between
collection centers). That is a move inside the Collector echelon,
not an ordering echelon, so no bullwhip echelon reads it
(ADR 0009).

The chain is doubly exogenous. Both market consumption and waste
generation are exogenous, so amplification enters in the middle
instead of growing toward the source. The denominator anchor is
consumption `attempted` (the exogenous demand presented), never
`consumed`, which stockouts have already shaped.

The source floor is measured on **potential generation** (the
volume the source process offers each tick, before the storage
cap), not **committed generation** (`total_generated`, what
actually entered storage). Storage headroom caps committed
generation, and finite-storage backpressure couples that cap to
policy. Its CV^2 therefore carries a policy signal (it swings
about 0.9 to 1.3 across the six combos). The potential-based
floor is policy-invariant (byte-identical across combos).

Beside the two anchored _headline_ ratios sits a
**stage-by-stage diagnostic** (`treatment_stage`,
`collector_stage`) that shows _where_ amplification enters.
Treatment stage =
`CV^2(treatment inbound)/CV^2(consumption)`. Collector stage =
`CV^2(collector inbound)/CV^2(treatment inbound)`. The stages are
computed on the **system-pooled** per-echelon series (every node
summed before CV^2), not the per-node volume-weighted aggregation
the headline uses. Only at the pooled level do they telescope
exactly to the anchored ratio
(`treatment_stage x collector_stage = pooled collector anchored`),
because a product of per-node weighted averages is not the
weighted average of products. So `treatment_stage` is the
_pooled_ Treatment ratio. It sits below the per-node
`treatment_anchored` headline, because pooling smooths
out-of-phase spikes.

The same pooled per-echelon series also backs a
**pooled robustness variant** (`treatment_anchored_pooled`,
`collector_anchored_pooled`). These are the anchored ratios
recomputed pooled instead of per-node-volume-weighted, a
conservative lower bound on the headline. If pooled still shows
PUSH > PULL, the result is strong. `treatment_anchored_pooled`
equals `treatment_stage` by construction (same pooled-treatment
CV^2 over consumption). `collector_anchored_pooled` equals the
telescoped product `treatment_stage x collector_stage`. Both keys
are emitted anyway, so the robustness pair reads in parallel
beside the headline pair.

Method and rationale are in ADR 0004, refined by ADR 0005
(floor), ADR 0006 (stage telescoping aggregation level), ADR 0007
(pooled variant emits both echelon keys despite the Treatment
identity), ADR 0009 (Treatment inbound is collector intake, not
the transport-log repositioning), and ADR 0019 (reorder decisions
use on-hand stock only and exclude in-transit volume, which
interacts with lead-time length under SupplyDisruption).
_Avoid_: order bullwhip (the metric is flow-based, not
order-based), bullwhip ratio (unqualified; say which echelon
and that it is CV^2-normalized), generation floor on
committed/`total_generated` (the floor is on potential
generation, and committed carries a policy signal)

**Seasonal Pattern**:
A quarter-discretized sinusoidal factor
`1 + 0.2 * sin(2*pi*q/4)`, where `q` is the 0-based quarter of the
365-day year (`utils/seasonality.py`). It is a step function, not
a continuous curve: 1.0 in Q1 (days 0-90), 1.2 in Q2 (peak),
1.0 in Q3, 0.8 in Q4 (trough), with jumps at the quarter
boundaries. It applies to both waste generation rates and market
consumption rates, so the same seasonality drives supply and
demand.
_Avoid_: seasonal index
(ambiguous, could refer to the array index or the factor value)

**Consumption Tick**:
The weekly interval (every 7 time units) at which the
**Market Consumption** process removes products from treatment
operators' finished goods inventory. Each tick consumes
`(annual_demand / 52) * seasonal_factor` per product type,
distributed across operators.
_Avoid_: consumption rate, sales cycle

**Lost Sales**:
When available finished goods cannot cover a
**Consumption Tick**, the unfulfilled portion is lost because the
market sourced it from a competitor. The shortfall counts against
**Service Level**. No backlog carries over to the next tick. Each
lost sale is tagged by reason: `no_capability` (the operator has
no transformation pathway for the requested product) or
`stockout` (the operator could produce it but had too little
stock). Per-operator service level reports both components
separately. System-level service level aggregates them.
_Avoid_: stockout
(as a general term; use the specific reason tags)

**Uncollected Waste**:
Waste a generator produces while its storage is full. Generation
is offered every period (**potential generation**), but only the
part that fits in storage enters the system (**committed
generation**). The rest is uncollected. It leaves the modelled
system with no known destination, so it carries no landfill cost
or emissions. It is counted per generator and waste type, and the
generator mass balance checks
`potential = committed + uncollected` (ADR 0024).
_Avoid_: landfill (landfill is overflow after collection),
lost waste

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
priority weights enter transformation selection scoring at a
2.0x multiplier, so ABC is the dominant factor in what a
**Treatment Operator** produces when several transformations are
available. It is always enabled, and every processor runs with
the same classification. This is not Activity-Based Costing. It
is an environmental-impact Pareto ranking.
_Avoid_: Activity-Based Costing, cost classification

**Run**:
One invocation of `main.py` and the entire batch of simulations it
produces. A grid run executes one simulation per policy/strategy
combo. A baseline run executes N replications per combo.
Individual simulations within a baseline run are replications,
not runs. The planned layout (plans 009-011, not yet built) names
each run with a generated **Run Name** and keeps all its
artifacts (config snapshot, results, plots, per-replication data)
in a single run directory. Baseline runs currently write to
`outputs/baseline/{scenario}/`.
_Avoid_: experiment, trial, execution

**Run Name**:
Planned, not yet built (plans 009-011). An auto-generated slug
that identifies a run: `{mode}_{variant}_{flags}__{HHMM}`. Mode
is the execution shape (`grid`, `baseline`). Variant is the
scenario filter, present only when `--scenario` restricts the run
to one scenario (omitted when running all scenarios). Flags are
non-default parameters (`n50` for 50 replications). The `__HHMM`
suffix separates same-config runs on the same day.
_Avoid_: run ID, job name

**Initial Inventory**:
Every echelon starts with 2 weeks of inventory at the expected
consumption rate. Treatment operators' `finished_goods` starts at
`(annual_demand / 52) * 2 * market_share` per product type, which
is 50% of `finished_goods_capacity` (sized for four weeks). That
leaves equal headroom for over- and under-production. Waste
storage starts with enough waste to produce 2 weeks of product
(the 2-week product target divided by blended transformation
efficiency), split across the operator's input waste types in
proportion to the region's waste generation mix. Collectors and
generators use the existing `initial_stock` from the region JSON.
PUSH and PULL start from the same initial conditions, which keeps
the comparison fair and avoids cold-start artifacts in
early-simulation metrics.
_Avoid_: warm-up stock, safety stock (different concept)

**Holding Cost**:
The waste-side inventory carrying cost. Each daily monitor sample
accrues `stored m³ x WASTE_HOLDING_COST_PER_M3_PER_DAY` on the
waste currently in storage at all three echelons: generator
storage, the collector's collection-center storage, and the
**Treatment Operator**'s `waste_storage`. **Finished Goods** are
excluded on purpose, since they are a different commodity with a
different carrying rate (future work). It is recorded as a
per-entity `holding_costs` series, separate from the
transport/processing cost series, and summed into the
`holding_cost` KPI, the fourth component of `total_system_cost`.
The rate ($0.005/m³-day, about $1.83/m³-year) is an uncalibrated
placeholder like the carbon shadow price. Flag it in the paper
before any cost claim depends on it. It is policy-sensitive by
design: configurations that park more waste upstream pay for it
(ADR 0017).
_Avoid_: storage cost (ambiguous with the overflow
expansion/landfill costs), warehousing cost, inventory cost
(too generic)

**Avoided Emissions**:
The greenhouse-gas emissions the system avoids by displacing
**virgin-feedstock production** of the same wood-based product.
Every MDF / particle board / OSB unit is made from recovered wood
waste, so it replaces a functionally identical panel that would
otherwise have been made from primary (virgin) wood, and the
footprint of that virgin production is avoided. The metric is
recycled **produced volume** per product type, scaled by a
per-product literature factor. It is a _recycling avoided-burden_
(secondary vs primary production of the same good), **not** a
material-substitution claim. The model does not represent the
buyer choosing wood over concrete/steel/plastic, so it asserts no
non-wood displacement. It is reported as a benefit next to the
operational emissions in `total_emissions_kgco2e`, on a different
system boundary.
_Avoid_: substitution effect (implies non-wood material
displacement), displacement factor (that is the per-carbon-mass
material-substitution metric, a different concept), carbon credit

**Biogenic Carbon Stored**:
The biogenic carbon locked into the panels the system produces,
reported as a static, production-weighted credit:
`Σ_product (produced_volume_p × biogenic_carbon_stock_p)`, summed
across **Treatment Operators**. The per-m³ stock is
`ProductSpecification.biogenic_carbon_stock`
(`models/products.py`). The sign convention is
**negative = sequestered** (carbon held out of the atmosphere),
so the credit reads negative beside the positive operational
`total_emissions_kgco2e`. It is the **static** stock view, _not_
the time-integrated / dynamic GWP-bio (Levasseur) view. That view
needs a product service life and an end-of-life release profile,
which the model lacks because it stops at **Market Consumption**.
It is named as future work, not computed. This is one of three
orthogonal carbon lines reported **side by side, never netted**
(ADR 0011): biogenic-stored (this), **Avoided Emissions**, and
operational `total_emissions_kgco2e`. The orthogonality is
binding. Biogenic carbon is excluded from
`total_emissions_kgco2e`, and the avoided-emissions factors
exclude biogenic carbon too, so the three lines never
double-count.
_Avoid_: GWP-bio / dynamic-LCA (this is the static stock, not the
time-integrated view), carbon sequestration credit (overclaims a
permanence the single-cycle model does not assert), net carbon
(the lines are not netted)

**Cascading Depth**:
The number of successive use-cycles a material passes through
before final disposal. In this model it is **1**. A
**Treatment Operator** transforms each unit of wood waste exactly
once, into a finished good (MDF / particle board / OSB) that
leaves the system boundary at **Market Consumption**. No path
returns a manufactured product to the waste stream for
re-treatment, so the mass ledgers close on a single
waste-to-product cycle. Multi-cycle cascading (product reuse, a
recovered panel re-entering as feedstock, sequential
down-gauging across product grades) is **future work** and not
modelled. It is reported as a documented modelling assumption
(depth = 1) and deliberately **not** as a per-run KPI. A constant
carries no Monte Carlo or paired-statistics signal, so a column of
`1.0`s would add nothing. The stated assumption answers the
reviewer question "did you consider cascading reuse?".
_Avoid_: reuse count, recycling loops (plural; there is one
cycle), number of lifecycles (the model has no product use phase)

**Stochastic Dominance (FSD / SSD)**:
A distribution-level comparison of two configurations over the
Monte Carlo **Run** distribution of a KPI, stronger than comparing
means. **First-order (FSD)**: `F_A(x) <= F_B(x)` for all `x`
(A's CDF lies entirely at or below B's). A is then stochastically
larger, and every decision maker with increasing utility prefers
it, whatever their risk attitude. **Second-order (SSD)**: the
integrated-CDF condition `∫F_A <= ∫F_B` for all `x`. Every
**risk-averse** (increasing, concave-utility) decision maker
prefers A. FSD implies SSD, so the report names the strongest
order that holds. The dominance math is **sense-free**. It works
on raw KPI values and answers only which distribution is
stochastically larger. Whether _larger_ is _better_ is the
per-KPI **sense** (service: larger better; emissions, landfill,
cost: larger worse), carried as a separate annotation. It
complements the CRN-paired mean-difference test. It reads the
same `run_*.json` set but uses the marginal distributions, which
seed pairing does not change.
_Avoid_: significance test (dominance is not a p-value claim),
"better distribution" (state the order and the sense separately)

**Time-Weighted WIP (Little's Law)**:
Average residence time recovered from inventory and throughput via
Little's Law `L = λ·W`, so `W = L/λ`. Here `L` is the
**time-averaged** work-in-process (not a point-in-time level) and
`λ` is throughput. WIP is the trapezoidal area under the
inventory history divided by the run horizon, so a level held for
a long interval weighs more than a brief spike. Partial coverage
extrapolates flat and does not bias the mean. It is applied per
stage with stage-specific inventory sources (generator/collector
storage, treatment buffer).
_Avoid_: instantaneous WIP (the law needs the time-average),
queue length (this is inventory, measured in m³)

## Example dialogue

> **Dev**: "The simulation finishes at day 100. All demands
> are met."
> **Domain expert**: "That's wrong. The demand envelope is
> 30,000 m^3 of OSB _per year_. The market consumes that over
> 365 days. If processors produce faster than the market
> consumes, product piles up in finished goods inventory. That
> doesn't mean demand is 'met.' Service level measures whether
> we keep up with consumption, not whether we hit a ceiling."
