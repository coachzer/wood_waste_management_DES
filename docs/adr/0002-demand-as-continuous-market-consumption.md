# Demand as continuous market consumption, not a production ceiling

The original model treated national demand (100k m3/year across MDF, particle board, OSB) as a one-shot ceiling: once cumulative production crossed the target, `get_unmet_demands()` returned zero and all processors idled for the remainder of the 365-day run. Adding more waste types with transformation pathways caused the ceiling to be hit by day ~100, making the simulation useless for the remaining 265 days.

We replaced this with a market consumption process: a SimPy process that fires weekly, removes products from treatment operators' `product_to_sell` storage at a seasonally-modulated rate, and records fulfilled vs unfulfilled consumption. The annual demand envelope is the same 100k m3 — what changed is that it's consumed continuously over the year rather than checked as a cumulative ceiling.

This decision reshapes the entire control architecture:

- **PUSH operators** react to inventory drops caused by consumption (no explicit notification). Storage capacity is the implicit production target — no separate forecast parameter.
- **PULL operators** receive explicit consumption events via KanbanManager (`source_type="market"`), which cascade upstream to collectors and generators through the existing signal infrastructure.
- **Service level** becomes `total_consumed / total_attempted` computed from weekly consumption events — meaningful from day 1, not a binary hit/miss at year end.
- **Lost sales** are tagged by reason (`no_capability` vs `stockout`) to separate structural production gaps from operational failures.
- **Consumption is distributed** proportionally to each operator's processing capacity (set as `market_share` at construction time), uniform across all product types — operators that can't produce a product type see structural lost sales, which surfaces policy-relevant insights about regional capacity gaps.

## Considered options

- **Time-proportional demand**: `unmet = (target * fraction_of_year) - consumed`. Rejected because it conflates demand arrival with production triggering, bakes in linearity that makes seasonal extension painful, and creates edge cases (formula goes negative if system runs ahead) with no clean operational interpretation.
- **Per-product market share**: Only distribute consumption for products an operator can actually make. Rejected because it hides structural gaps that are policy-relevant for circular economy analysis (e.g., a region with no MDF capability has real unmet demand that suggests cross-regional transport or capacity investment).
- **Backlog instead of lost sales**: Unfulfilled consumption carries over. Rejected for now — lost sales is more realistic for commodity wood products (buyers don't wait), and it makes the service level metric harsher and more discriminating between strategies. Backlog is noted as a future research option.

## Consequences

- `_distribute_demand()` in SimulationManager deletes. Replaced by `market_share` parameter on each operator, set at construction.
- `SimulationState.get_unmet_demands()`, `check_all_demands_met()`, `demand_met_times` all delete.
- `processor.demand` as a persistent attribute deletes — neither set at init nor read meaningfully.
- `_apply_stock_strategy_to_demand_calculation()` deletes or refactors to operate purely on inventory levels.
- PUSH/PULL contrast becomes more rigorous: "produce based on own inventory state" vs "produce in response to downstream consumption events."
- Service level becomes a harsher metric than the old ceiling model. PUSH strategies may perform relatively better than in prior results because their over-production cushion genuinely protects against stockouts in a way the old metric didn't reward. This shift in relative performance is itself a finding worth reporting.
