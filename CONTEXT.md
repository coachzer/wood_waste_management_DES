# Wood Waste Management DES

Discrete event simulation of wood waste collection, treatment, and product manufacturing in Slovenia. Models the flow from waste generation through collection and treatment into final wood-based products (MDF, particle board, OSB).

## Language

**Demand Envelope**:
The total annual volume of each product type that the market consumes over a 365-day simulation run. Specified as an annual total in `demand.json`, consumed continuously via a market consumption process.
_Avoid_: quota, target, order

**Market Consumption**:
A SimPy process that periodically removes finished products from treatment operators' sell storage, simulating buyers taking delivery. Drives the demand signaling rate and keeps processors active throughout the simulation year.
_Avoid_: sales, shipment

**Service Level**:
The fraction of demand that was fulfilled when consumption occurred. Only meaningful because demand arrives continuously — a one-shot quota would yield binary hit/miss.
_Avoid_: fill rate, completion rate

**Treatment Operator**:
A production facility that converts waste into final products. In PUSH mode, replenishes based on internal inventory thresholds. In PULL mode, produces in response to **Consumption Events**.
_Avoid_: processor, factory

**PUSH (Inventory Policy)**:
Each entity reasons from its own observable state — inventory levels, storage utilization, reorder points. Information does not flow downstream-to-upstream as events. The **Market Consumption** process drains `product_to_sell` but does not notify PUSH operators; they detect the inventory drop via their **Stock Strategy** thresholds. Physical storage capacity serves as the implicit production target — there is no separate forecast or `target_inventory` parameter. PUSH-ON_DEMAND = produce until full; PUSH-REORDER_50 = produce until 50% of capacity. Structurally: make-to-stock without explicit forecast.
_Avoid_: forecast-driven, planned

**PULL (Inventory Policy)**:
The trigger is the downstream consumption event itself, not the inventory drop it causes. When the **Market Consumption** process pulls from a PULL operator, that operator receives an explicit **Consumption Event** with volume. The operator decides whether to produce (gated by **Stock Strategy** on `product_to_sell`), checks waste storage, and if waste is insufficient, signals upstream — also gated by stock strategy. The signal chain is causal: consumption causes production, production causes upstream waste demand, upstream waste demand causes collector activity. No autonomous inventory polling. Structurally: make-to-order / JIT.
_Avoid_: reactive, demand-driven (too vague)

**Consumption Event**:
An explicit notification from the **Market Consumption** process to a PULL **Treatment Operator** that product was consumed (or attempted). Carries the product type and volume. Delivered via **KanbanManager** with `source_type="market"`, making the PULL cascade uniform: market → treatment → collector → generator, all through the same signal infrastructure.
_Avoid_: demand signal, order

**Demand Signal**:
A request from a **Treatment Operator** to collectors (and transitively to generators) for a specific waste type and volume. In PULL mode, triggered by **Consumption Events**. In PUSH mode, triggered by stock strategy thresholds detecting low inventory.
_Avoid_: order, request

**Seasonal Pattern**:
A sinusoidal factor `1 + 0.2 * sin(2πt/T)` applied to both waste generation rates and market consumption rates. Peaks in summer (more construction activity), troughs in winter. Shared between generators and consumption so that supply and demand are driven by the same underlying seasonality.
_Avoid_: seasonal index (ambiguous — could refer to the array index or the factor value)

**Consumption Tick**:
The weekly interval (every 7 time units) at which the **Market Consumption** process removes products from treatment operators' sell storage. Each tick consumes `(annual_demand / 52) * seasonal_factor` per product type, distributed across operators.
_Avoid_: consumption rate, sales cycle

**Lost Sales**:
When a **Consumption Tick** cannot be fully fulfilled from available sell storage, the unfulfilled portion is lost — the market sourced from a competitor. The shortfall counts against **Service Level**. No backlog carries over to the next tick. Each lost sale is tagged by reason: `no_capability` (operator has no transformation pathway for the requested product) or `stockout` (operator could produce it but had insufficient stock). Per-operator service level reports both components separately; system-level service level aggregates them.
_Avoid_: stockout (as a general term — use the specific reason tags)

**Consumption Distribution**:
Each **Treatment Operator**'s share of weekly **Market Consumption** is proportional to its processing capacity relative to the national total. A facility with 64,000 m³ capacity absorbs more consumption than one with 14,400 m³. Each facility has its own effective regional market share.
_Avoid_: market allocation, demand split

**Run**:
One invocation of `main.py` — the entire batch of simulations it produces. A grid run executes one simulation per policy/strategy combo; a baseline run executes N replications per combo. Individual simulations within a baseline run are replications, not runs. Runs are identified by a generated name encoding mode, variant, and flags, and all artifacts (config snapshot, results, plots, per-replication data) live in a single run directory.
_Avoid_: experiment, trial, execution

**Run Name**:
An auto-generated slug that identifies a run at a glance: `{mode}_{variant}_{flags}__{HHMM}`. Mode is the execution shape (`grid`, `baseline`). Variant is the scenario filter, present only when `--scenario` restricts to one (omitted when running all scenarios). Flags are non-default parameters (`n50` for 50 replications). The `__HHMM` suffix disambiguates same-config runs on the same day.
_Avoid_: run ID, job name

**Initial Inventory**:
All echelons are primed with 2 weeks of inventory at expected consumption rate before simulation starts. Treatment operators' `product_to_sell` is initialized to `(annual_demand / 52) * 2 * market_share` per product type. Waste storage is initialized to enough waste to produce 2 weeks of product (adjusted by transformation efficiency). Collectors and generators use existing `initial_stock` from region JSON. Same initial conditions for both PUSH and PULL — ensures fair comparison and avoids cold-start artifacts in early-simulation metrics.
_Avoid_: warm-up stock, safety stock (different concept)

## Example dialogue

> **Dev**: "The simulation finishes at day 100 — all demands are met."
> **Domain expert**: "That's wrong. The demand envelope is 30,000 m³ of OSB *per year*. The market consumes that over 365 days. If processors produce faster than the market consumes, product piles up in sell storage — it doesn't mean demand is 'met.' Service level measures whether we keep up with consumption, not whether we hit a ceiling."
