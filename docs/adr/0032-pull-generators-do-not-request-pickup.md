# PULL generators do not request pickup

Date: 2026-11-18
Status: accepted

## Context

CONTEXT.md and ADR 0025 define PULL as downstream-triggered: market consumption, then treatment,
then collector, then generator. The code did not match. A PULL generator posted a pickup signal:

- under REORDER_50 and REORDER_90, when its storage passed 50% or 90% of capacity, and
- under ON_DEMAND, whenever any signal anywhere was on the shared bus.

Collectors served those signals, so most PULL collection was pushed by generators. Before ADR 0031,
PULL depended on this: without generator signals it served only 58-70%.

## Decision

`InventoryPolicy.generators_request_pickup()` is True for PUSH and False for PULL.
`WasteGenerator._handle_inventory_signaling` posts nothing when it is False. PULL collectors
still pass treatment orders upstream to generators as collector signals. Those come from demand
and stay. `PullPolicy.ondemand_generator_should_signal` had no caller left and is removed.

PUSH is unchanged (all 30 PUSH runs byte-identical, seeds 1-10).

## Consequences

Seeds 1-10, Baseline, PULL minus PUSH (paired, 95% CI), with ADR 0031:

| Strategy | Service, pts | Collection rate, pts | Uncollected, m3 | Cost, model currency M |
|---|---|---|---|---|
| ON_DEMAND | -0.66 [-0.89, -0.44] | -48.6 | +191k [+175k, +208k] | -0.86 [-0.90, -0.82] |
| REORDER_50 | 0.0 | -58.2 | +239k [+237k, +241k] | -1.06 [-1.08, -1.05] |
| REORDER_90 | 0.0 | -75.0 | +237k [+234k, +239k] | -1.33 [-1.35, -1.30] |

- PULL collects 13% of generation in every strategy, about what treatment converts. PUSH collects
  61-88%, and most of it waits in collection centers.
- The PULL uncollected volume (231-239k m3, 23-24%) is waste nobody ordered. About half of
  generation is a code no processor accepts.
- Treatment-anchored bullwhip, PULL minus PUSH, fell to +1.3, +0.16 and +0.25, from +8.3, +5.1 and
  +12.6.
- PULL ON_DEMAND still serves 99.3%. The probe in `.scratch/agy-needs/` shows that signalling a
  surplus region closes the gap (agy's Fix B). That fix would let each operator see every
  generator's stock nationwide, so it was not adopted.
