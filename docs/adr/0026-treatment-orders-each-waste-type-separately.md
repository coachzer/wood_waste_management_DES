# Treatment orders each waste type separately

Date: 2026-11-18
Status: accepted

## Context

Treatment ordered one total volume across all its input types. `trigger_collection` passed that
total and the sorted type list to `request_waste_directly`, and collectors filled it type by type in
sorted EWC order. The first sorted type with stock took the whole order. With the order-up-to level
at storage capacity (ADR 0002), orders were large enough that later types usually still got some.
With a level sized to demand (ADR 0027), they did not. On seed 1, PUSH REORDER_50, the OSB-capable
inputs (03 01 99, 15 01 03, 17 02 01, which sort last) sat at zero on 330-365 days at several
operators while local collectors held thousands of m3 of them, and OSB stockouts reached 76%.

PULL already split its signals per type (evenly), but the drain that both policies share did not.

## Decision

Treatment runs a multi-item (s, S): one order-up-to level per input type.

- A type's level is its share of the treatment order-up-to level (storage capacity here, the
  sized level from ADR 0027).
- Shares come from product need. Each producible product needs `demand / mean route efficiency`
  waste. That need is spread over the types that can make it by the **national** generation mix,
  because collection crosses regions. A regional mix gave zero share to types the home region does
  not generate, and those were then never ordered.
- Each type reorders when its own stock is below the strategy fraction of its own level, orders
  the gap to its level, and is requested from collectors on its own.
- PULL signals carry each type's order volume instead of an even split of the total.

Both policies use the same shares and levels.

## Consequences

Paired over seeds 1-10, Baseline, against ADR 0025, with the level still at storage capacity:

- REORDER_50 and REORDER_90: service level within +1 point, collection transport cost 4-14%
  lower, treatment-anchored bullwhip lower.
- ON_DEMAND: service level falls, by 5.6 points [4.4, 6.9] for PUSH and 4.2 [2.8, 5.6] for PULL.
  The cause is hoarding. ON_DEMAND orders every type every tick up to its share of a capacity
  worth about three years of throughput. The operators polled first (eastern regions) fill
  their 15 01 03 share from the whole country, and western operators, whose collectors hold almost
  no OSB-capable waste, run out (goriska OSB 90% short on seed 1). The old sorted drain hid this
  because the eastern operators filled up on early-sorted types first.

This is an artifact of a capacity-sized level, and ADR 0027 removes it. It is committed
separately so the two effects can be told apart.
