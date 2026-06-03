# Wood Waste Management DES

Discrete event simulation of wood waste collection, treatment, and product manufacturing in Slovenia. Models the flow from waste generation through collection and treatment into final wood-based products (MDF, particle board, OSB).

## Language

**Demand Envelope**:
The total annual volume of each product type that the market consumes over a 365-day simulation run. Specified as an annual total in `demand.json`, consumed continuously via a market consumption process.
_Avoid_: quota, target, order

**Market Consumption**:
A SimPy process that periodically removes finished products from treatment operators' finished goods inventory, simulating buyers taking delivery. Drives the demand signaling rate and keeps processors active throughout the simulation year.
_Avoid_: sales, shipment

**Service Level**:
The fraction of demand that was fulfilled when consumption occurred. Two derived metrics from the same consumption-event log:
- `full_service_level` (headline) = `total_consumed / total_attempted` — includes both `no_capability` and `stockout` lost sales. Used as the cross-policy comparator because the `no_capability` floor is identical across all six PUSH/PULL × strategy configurations (same regional capability layout).
- `operational_service_level` (diagnostic) = `total_consumed / (total_attempted - no_capability_lost)` — measures policy effectiveness on demand the system can actually fulfill. Strips the structural floor to expose pure operational performance.

Per-operator and per-product breakdowns derive from the same event log by filtering. Only meaningful because demand arrives continuously — a one-shot quota would yield binary hit/miss.
_Avoid_: fill rate, completion rate, feasible service level (use `operational_service_level`)

**Treatment Operator**:
A production facility that converts waste into final products. In PUSH mode, replenishes based on internal inventory thresholds. In PULL mode, produces in response to **Consumption Events**.
_Avoid_: processor, factory

**Finished Goods**:
A **Treatment Operator**'s buyer-facing inventory of completed products (MDF, particle board, OSB). Drained by **Market Consumption**, filled by production. Capacity is **per product type**: `finished_goods_capacity[P] = market_share × (annual_demand[P] / 52) × 4` (four weeks of *that product's* expected consumption); the operator's aggregate buffer is their sum. **Initial Inventory** primes each product at 50% (two weeks). Production is clamped per output type to that product's remaining headroom — a saturated OSB buffer throttles OSB transformations even when MDF has headroom. Replaces the prior two-buffer `product_to_sell` + `product_storage` design; the secondary buffer had no drain path and was always vestigial.
_Avoid_: product_to_sell (old name), inventory (too generic — could mean waste_storage too)

**PUSH (Inventory Policy)**:
Each entity reasons from its own observable state — inventory levels, storage utilization, reorder points. Information does not flow downstream-to-upstream as events. The **Market Consumption** process drains `finished_goods` but does not notify PUSH operators; they detect the inventory drop via their **Stock Strategy** thresholds. Physical storage capacity serves as the implicit production target — there is no separate forecast or `target_inventory` parameter. PUSH-ON_DEMAND = produce until full; PUSH-REORDER_50 = produce until 50% of capacity. Structurally: make-to-stock without explicit forecast.
_Avoid_: forecast-driven, planned

**PULL (Inventory Policy)**:
The trigger is the downstream consumption event itself, not the inventory drop it causes. When the **Market Consumption** process pulls from a PULL operator, that operator is woken by the per-tick **Market Signal** and reads its **Consumption Events** for the tick, producing each product up to that product's `attempted` volume, subject to the partial-batch headroom clamp on `finished_goods`. The **Stock Strategy** gates upstream waste-side replenishment only: after production consumes input waste, if `waste_storage` has dropped below the strategy threshold, the operator signals upstream collectors. Production responds to every event regardless of `finished_goods` level — strategy does not target a downstream buffer. The signal chain is causal: consumption causes production; production causes upstream waste demand when the strategy threshold is crossed; upstream waste demand causes collector activity. No autonomous polling on `finished_goods`. Structurally: lot-for-lot downstream, `(s, S)` policy upstream.
_Avoid_: reactive, demand-driven (too vague)

**Stock Strategy**:
The local waste-side replenishment policy applied at each entity. Three variants:
- `ON_DEMAND`: signal upstream lot-for-lot — every waste consumption triggers a signal for replacement volume
- `REORDER_50`: signal upstream when `waste_storage` drops below 50% of `waste_storage_capacity`
- `REORDER_90`: signal upstream when `waste_storage` drops below 90% of capacity

Strategy gates waste-side decisions only (when upstream signals fire). Does not gate `finished_goods` production: in **PUSH**, production triggers on autonomous waste-state polling against the same threshold; in **PULL**, production triggers on **Consumption Event** arrival regardless of strategy. The strategy parameter sets the reorder point (`s` in `(s, S)` notation). The order-up-to level is `S = waste_storage_capacity` — when threshold breached, the signal volume is `waste_storage_capacity - current_waste_storage` (order up to full capacity). ON_DEMAND under this rule is lot-for-lot: s = S = capacity, signal_volume = amount-just-consumed.
_Avoid_: reorder policy (overloaded), inventory policy (that's PUSH/PULL)

**Consumption Event**:
The record of a single market consumption attempt against one **Treatment Operator** for one product, written to the consumption-event log on `SimulationState`. Carries product type, `attempted` volume (full demand including any unfulfilled portion), `consumed`, and the **Lost Sales** reason. The log is the authoritative per-product record and the basis for **Service Level**.

A PULL operator is *notified* that consumption occurred by a single per-tick **Market Signal** (delivered via **KanbanManager**, `source_type="market"`) carrying its total producible `attempted` volume — an edge trigger, not the payload. On that trigger the operator reads its Consumption Events for the tick from the log and sets each product's production target to that product's `attempted`, so a stockout on tick N does not silence production on tick N+1 (no death-spiral). Lost-sale tracking stays at the `SimulationState` level; the operator never needs `consumed` or `lost`. The aggregate Market Signal keeps the PULL cascade uniform (market → treatment → collector → generator) while per-product demand comes from the log.
_Avoid_: demand signal, order

**Market Signal**:
The per-tick, per-operator edge trigger emitted by **Market Consumption** to a PULL **Treatment Operator** (via **KanbanManager**, `source_type="market"`), carrying the operator's total producible `attempted` volume for that **Consumption Tick**. It wakes the operator and is acknowledged once; the per-product production targets come from the **Consumption Event** log, not from this signal. Distinct from a **Demand Signal**, which is the operator's downstream waste-side request to collectors.
_Avoid_: consumption signal, market order

**Demand Signal**:
A request from a **Treatment Operator** to collectors (and transitively to generators) for a specific waste type and volume. In PULL mode, triggered by **Consumption Events**. In PUSH mode, triggered by stock strategy thresholds detecting low inventory.
_Avoid_: order, request

**Throughput Bullwhip**:
The variance amplification of *physical replenishment flow* relative to market demand, measured per ordering echelon as the cross-policy PUSH-vs-PULL evidence. Defined on **delivered flow** (from the transport-flow log), not on **Demand Signals** — those are not observable in PUSH (collectors ignore generator signals) and are not persisted, so flow is the only quantity logged identically under both policies. Normalized as a squared coefficient of variation ratio, `CV²(echelon weekly inbound flow) / CV²(weekly market consumption)`, so the value is unit-free across the waste-to-product commodity change and `> 1` means amplification. There are **two ordering echelons** — Treatment (`collector→treatment` flow) and Collector (`generator→collector` flow); waste **generation** is an exogenous *source-variance floor*, not a third echelon, because generators do not order. This is a doubly-exogenous chain — both market consumption and waste generation are exogenous — so amplification is injected in the middle, not grown toward the source. The denominator anchor is consumption `attempted` (the exogenous demand presented), never `consumed` (already shaped by stockouts). Method and rationale: ADR 0004.
_Avoid_: order bullwhip (the metric is flow-based, not order-based), bullwhip ratio (unqualified — say which echelon and that it is CV²-normalized)

**Seasonal Pattern**:
A sinusoidal factor `1 + 0.2 * sin(2πt/T)` applied to both waste generation rates and market consumption rates. Peaks in summer (more construction activity), troughs in winter. Shared between generators and consumption so that supply and demand are driven by the same underlying seasonality.
_Avoid_: seasonal index (ambiguous — could refer to the array index or the factor value)

**Consumption Tick**:
The weekly interval (every 7 time units) at which the **Market Consumption** process removes products from treatment operators' finished goods inventory. Each tick consumes `(annual_demand / 52) * seasonal_factor` per product type, distributed across operators.
_Avoid_: consumption rate, sales cycle

**Lost Sales**:
When a **Consumption Tick** cannot be fully fulfilled from available finished goods inventory, the unfulfilled portion is lost — the market sourced from a competitor. The shortfall counts against **Service Level**. No backlog carries over to the next tick. Each lost sale is tagged by reason: `no_capability` (operator has no transformation pathway for the requested product) or `stockout` (operator could produce it but had insufficient stock). Per-operator service level reports both components separately; system-level service level aggregates them.
_Avoid_: stockout (as a general term — use the specific reason tags)

**Consumption Distribution**:
Each **Treatment Operator**'s share of weekly **Market Consumption** is proportional to its processing capacity relative to the national total. A facility with 64,000 m³ capacity absorbs more consumption than one with 14,400 m³. Each facility has its own effective regional market share.
_Avoid_: market allocation, demand split

**ABC Classification**:
A Pareto-style prioritization of output products (OSB, particle board, MDF) by total biogenic carbon stock impact. Products are ranked by `demand_volume × biogenic_carbon_per_unit`, then classified: Class A (cumulative ≤70%, weight 1.0), Class B (≤95%, weight 0.7), Class C (remainder, weight 0.4). Current classification: OSB = A, particle board = B, MDF = C. The priority weights feed into transformation selection scoring at a 2.0× multiplier, making ABC the dominant factor in what a **Treatment Operator** produces when multiple transformations are available. Always enabled — every processor runs with the same classification. Not traditional Activity-Based Costing; this is an environmental-impact Pareto ranking.
_Avoid_: Activity-Based Costing, cost classification

**Run**:
One invocation of `main.py` — the entire batch of simulations it produces. A grid run executes one simulation per policy/strategy combo; a baseline run executes N replications per combo. Individual simulations within a baseline run are replications, not runs. Runs are identified by a generated name encoding mode, variant, and flags, and all artifacts (config snapshot, results, plots, per-replication data) live in a single run directory.
_Avoid_: experiment, trial, execution

**Run Name**:
An auto-generated slug that identifies a run at a glance: `{mode}_{variant}_{flags}__{HHMM}`. Mode is the execution shape (`grid`, `baseline`). Variant is the scenario filter, present only when `--scenario` restricts to one (omitted when running all scenarios). Flags are non-default parameters (`n50` for 50 replications). The `__HHMM` suffix disambiguates same-config runs on the same day.
_Avoid_: run ID, job name

**Initial Inventory**:
All echelons are primed with 2 weeks of inventory at expected consumption rate before simulation starts. Treatment operators' `finished_goods` is initialized to `(annual_demand / 52) * 2 * market_share` per product type — 50% of `finished_goods_capacity` (which is sized for four weeks), giving symmetric headroom for over- and under-production phases. Waste storage is initialized to enough waste to produce 2 weeks of product (the 2-week product target divided by blended transformation efficiency), distributed across the operator's input waste types in proportion to the region's waste generation mix. Collectors and generators use existing `initial_stock` from region JSON. Same initial conditions for both PUSH and PULL — ensures fair comparison and avoids cold-start artifacts in early-simulation metrics.
_Avoid_: warm-up stock, safety stock (different concept)

## Example dialogue

> **Dev**: "The simulation finishes at day 100 — all demands are met."
> **Domain expert**: "That's wrong. The demand envelope is 30,000 m³ of OSB *per year*. The market consumes that over 365 days. If processors produce faster than the market consumes, product piles up in finished goods inventory — it doesn't mean demand is 'met.' Service level measures whether we keep up with consumption, not whether we hit a ceiling."
