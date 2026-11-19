# Decisions

Design decisions still in force. Headings keep the ADR numbers that code, tests and GLOSSARY.md cite. The code is the source of truth. Measured effects of each change are in git history, not here.

## 0002 Demand is continuous market consumption
A weekly market process (`_market_consumption_process`, `CONSUMPTION_INTERVAL_DAYS`) draws finished goods down at a seasonal rate, operator by operator, by `market_share`. Unmet demand is a lost sale, not a backorder, so service level stays harsh enough to separate strategies. Finished-goods capacity is per product (`FINISHED_GOODS_BUFFER_WEEKS` of expected consumption), and PUSH produces up to the per-product headroom. PULL production is driven by market signals (0020, 0029).

## 0004 Bullwhip is a CV²-normalized throughput-flow ratio
`BW = CV²(weekly inbound flow) / CV²(weekly market consumption attempted)`, per node over weeks after warm-up, volume-weighted across the echelon, averaged over replications. Two echelons (Treatment, Collector) are anchored to the same consumption CV². The textbook order-variance form does not fit: PUSH has no orders and the unit changes along the chain. Code: `analysis/bullwhip.py`.

## 0005 The source-variance floor uses potential generation
`generation_floor_cv2` reads `total_potential_generated`, not committed generation. Committed generation depends on storage headroom, so it carries a policy signal and is not a valid reference.

## 0006 Stage bullwhip telescopes only at the pooled level
`stage_bullwhip` uses system-pooled series per echelon, because a product of per-node weighted averages is not the weighted average of products. The per-node headline and the pooled stages are not expected to multiply out.

## 0007 Pooled robustness variant emits both echelon keys
`treatment_anchored_pooled` equals `treatment_stage` by construction, and is still emitted beside `collector_anchored_pooled` so the pair reads in parallel.

## 0008 Summary confidence intervals use Student-t
Every CI in `summary.csv` is `t(0.975, n-1) * stdev / sqrt(n)`, matching the paired comparison. With one replication the CI collapses to the mean.

## 0009 Treatment inbound is collector intake
The Treatment echelon reads `collector -> treatment` flows logged where `provide_waste_for_treatment` drains a collector. Cross-region repositioning is logged as `collector -> collector` and read by no echelon. The earlier `collector -> treatment` label on repositioning was wrong.

## 0010 Repositioned waste is not credited to treatment at request time
`_collect_from_cross_region` does not add repositioned volume to `collected_waste`. It lands in the destination collection center and reaches treatment on a later local intake. Crediting it at request time counted it twice, and the waste-side mass balance now enforces conservation.

## 0011 Avoided emissions are a recycling avoided-burden, never netted
Avoided emissions use per-product cradle-to-gate factors (Lao and Chang 2023, biogenic excluded) for the virgin panel a recycled panel replaces. The model has no material-substitution counterfactual. Avoided emissions, stored biogenic carbon and `total_emissions_kgco2e` are reported side by side and never subtracted, since their boundaries differ. Factors: `AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT`.

## 0013 Densities are per waste type
Transport emissions (`charge_trip`) and landfill cost (`utils/capacity_utils.py`) use `WASTE_DENSITIES` per type, not a flat 600 kg/m³. Per-type dict iteration is sorted by enum value. Currency restatement and cost-parameter sourcing are still open, and costs stay labelled USD in code.

## 0014 Entity status is persisted as the enum name
Monitors store `status.name` ("OPERATIONAL", "FAILED", "RECOVERING"), so reordering `EntityStatus` cannot remap old runs. Run JSONs written before this hold ints and should be regenerated.

## 0015 `transportation_time` is a road-circuity factor on travel time
It multiplies great-circle distance before dividing by `TRAVEL_SPEED_KMH`, clamped at 1.0. Collection trips draw it per trip from the collector's own RNG. Repositioning uses the deterministic mean, because the shared transport manager has no seeded RNG. It affects time only. Cost and emissions use `ROAD_CIRCUITY_FACTOR` (0038).

## 0016 OSB does not accept sawdust (03 01 05)
OSB needs strands, which sawdust cannot form. `WASTE_TO_OUTPUT_TYPES` maps 03 01 05 to particle board and MDF only. The thesis table that lists it for OSB is wrong, and the catalogue in `models/transformations.py` is the reference.

## 0017 Waste holding cost at all three echelons
`WASTE_HOLDING_COST_PER_M3_PER_DAY` is charged on waste storage at each daily monitor sample into a separate `holding_costs` series, summed into the `holding_cost` KPI and `total_system_cost`. Without it, PUSH and PULL inventory differences cost nothing. The rate is an uncalibrated placeholder. Finished goods are excluded.

## 0018 The kanban signal bus is load-bearing
Disabling propagation and processing of signals under PULL changes results a lot (`tests/test_kanban_effectiveness.py`). The bus gates collector behaviour rather than merely priming upstream supply. Its signal-loss paths were fixed by 0023 and 0025.

## 0019 Reorder decisions read on-hand stock only
No echelon counts in-transit volume when deciding to reorder. This amplifies stacking under long lead times (SupplyDisruption) and is intended. For treatment it equals the classical position when the local center holds the type, which is typically PUSH.

## 0020 Treatment and collectors run on a daily clock at unchanged annual capacity
`OPERATING_TICK_DAYS = 1.0`. `per_tick_capacity` rescales `processing_time` and `collection_frequency` capacities, so the region data keeps meaning "the period the capacity refers to". A PULL operator carries unmet targets in a production backlog (0029) and absorbs market signals even while FAILED. `KANBAN_SIGNAL_MAX_AGE_DAYS` equals one tick. PUSH collector jitter is removed. Vehicle capacity is one tick of collection.

## 0021 FAILED operators do not order, and treatment signals reach empty collectors
A FAILED `TreatmentOperator` waits a tick without polling. Treatment signals go to every available local PULL collector at the full needed volume, since an empty collector is the one that must pass demand to generators.

## 0022 PULL collectors stop at the utilization ceiling
A PULL collector serves signals only while its center is below `COLLECTOR_UTILIZATION_CEILING` (0.80), the same cap PUSH uses. Signals that forced collection into full centers were the source of PULL landfill.

## 0023 Collectors leave generator signals they cannot serve
A collector acknowledges a generator signal only when it collects against it. Unmatched signals stay on the bus until they expire, because another region's collector may be a legitimate server (`LOCAL_COLLECTION_RATIO`).

## 0024 Uncollected waste is counted
Generation offered while storage is full goes to `total_uncollected`, so `potential == committed + uncollected` (checked by `MassBalanceMonitor.check_generators`). It gets no landfill cost or emissions. Collection rate and overall efficiency divide by potential generation.

## 0025 PUSH and PULL collectors differ only in trigger
Collector efficiency is equipment aging only, identical across all six combinations. A PULL collector with no signal does nothing, and PUSH collects by volume below its threshold.

## 0026 Treatment orders each waste type separately
Treatment runs a multi-item (s, S) with one level per input type. Shares come from product need spread by the national generation mix, since collection crosses regions. Each type reorders against its own stock, and PULL signals carry each type's own order volume. PUSH and PULL use the same levels. Code: `_order_volumes_by_waste_type`.

## 0027 The treatment order-up-to level is sized from demand
`S = D * n + z * sigma * sqrt(n)`, clamped at storage capacity (`_order_up_to_level`, `SAFETY_STOCK_Z`). `D` is the waste needed per consumption interval from parameters, so PUSH and PULL get the same S. Lead time is taken as 0, which understates the position under PULL with an empty center. The same S for both policies is deliberate.

## 0028 A signal moves only the type it names
`collect_from_generator` takes a `waste_type`. A signalled pickup takes that stream only, capped at the signalled volume. PUSH pickups take every stream.

## 0029 PULL backlog is base-stock on sales
The backlog starts at finished-goods capacity minus initial stock, and each market signal adds the `consumed` volume. Finished goods plus backlog stay at the level PUSH produces up to, so only the trigger differs.

## 0030 Generation rates are calibrated to SURS
`data/calibrate_generation_rates.py` rebuilds every rate as the 2022-2024 mean of business generation plus municipal hand-over, per code and region, divided by 365. Codes SURS does not report for a region are left out. Capacities and demand were not recalibrated and may hold invented values.

## 0031 Collectors serve the largest treatment order first
`CollectorCompany._signals_in_dispatch_order` puts treatment signals before others, largest volume first. Only the newest treatment signal per operator and waste type is live, since summing older ones orders the same gap twice.

## 0032 PULL generators do not request pickup
`generators_request_pickup()` is True for PUSH and False for PULL, so under PULL only waste some operator ordered moves. Collector signals passed upstream from treatment orders stay.

## 0033 PULL operators signal a surplus region
If the order exceeds local stock (centers plus generators), `_propagate_signal_to_collectors` also signals the PULL collectors of the one other region whose generators hold the most of that type, for the deficit only. It assumes operators see generator stock nationwide, which overstates what PULL can coordinate.

## 0034 Inter-region transfers are priced
A completed transfer is charged through `CollectorCompany.charge_trip` like a collection trip, loaded leg only, paid by the vehicle's owner.

## 0035 Processors do not accept paper packaging (15 01 01)
15 01 01 is paper, not wood, and is not in any processor's `input_types`. Generators still produce it at its SURS rate. 20 01 38 stays.

## 0036 Codes no processor accepts leave through an outlet
`SimulationManager._nationally_accepted_waste_types` is the union of processor inputs. Any other code goes to `total_outlet` at generation, not into storage, so `potential = committed + uncollected + outlet`. Collection rate and overall efficiency divide by potential minus outlet, and `collection_rate_all_generation_pct` keeps the old denominator. Outlet destinations use SURS shares (`data/outlet_destination_shares.json`) for reporting only, with no cost or emissions.

## 0037 The cross-region fallback drain is priced
In `_drain_collectors`, a drain from another region is charged as one loaded trip through `charge_trip`. The drain still takes no travel time and no vehicle. That approximation remains.

## 0038 Transport cost and emissions use road distance
`charge_trip` multiplies great-circle distance by `ROAD_CIRCUITY_FACTOR` (1.35). It is a constant, not the scenario's `transportation_time`, so stress scenarios that slow transport do not inflate fuel and cost. It is deterministic, so no extra RNG draws. No primary source backs the 1.35 value.

## 0039 Transfer volume leaves the center when a vehicle loads it
`PointToPointTransport.process_requests` debits the origin when it assigns a vehicle, loading `min(requested, stock)`. Queued volume stays in center stock. `_get_available_waste_from_collector` subtracts `queued_volume` so one cross-region request cannot claim the same stock twice.

## 0040 Transfer vehicles return home, and FAILED fleets take no transfers
After delivery the vehicle drives home empty over road travel time and stays `in_transit` until it arrives. The leg has no per-km charge. `find_available_vehicle` skips vehicles of FAILED collectors, and a transfer already under way still delivers.

## Dropped numbers

- 0001 Run artifact directories: never implemented. No code writes `outputs/runs/`.
- 0003 Architecture deepening sequence: a plan, now history. `SimulationState` injection landed and is documented in `models/state.py`.
- 0012: never existed (the number was reserved for the freeze oracle ADR, since removed).
