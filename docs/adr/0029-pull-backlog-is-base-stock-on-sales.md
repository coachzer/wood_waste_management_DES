# PULL production backlog is base-stock on sales

Date: 2026-11-18
Status: accepted

## Context

The PULL production backlog added the `attempted` volume of each consumption event (ADR 0020).
Market shortfalls are lost sales, not backorders, so the backlog also booked production for sales
that never come back. It started empty, while PUSH produces up to finished-goods capacity from
day 0. The two policies therefore aimed at different finished-goods levels.

## Decision

- The backlog starts at finished-goods capacity minus initial finished goods (half of capacity).
- Each market signal adds the `consumed` volume of its consumption events.

Finished goods plus backlog then stays at capacity. This is a base-stock rule with lost sales:
replace what was sold, up to the same level PUSH produces up to. Only the trigger differs (ADR 0025).

The concern behind `attempted` (an emptied inventory starving production) does not arise: at zero
finished goods, the backlog is the full capacity.

## Consequences

Paired change against ADR 0028, seeds 1-10, Baseline. PUSH is unchanged (identical runs).

| Combo | Service level, % | Collection rate, % | Total system cost, EUR |
|---|---|---|---|
| PULL ON_DEMAND | +0.2 [-1.7, +2.0] | +0.3 [-0.2, +0.9] | -0.07 M [-0.51, +0.37] |
| PULL REORDER_50 | 0.0 | +0.4 [+0.1, +0.6] | +0.12 M [+0.08, +0.15] |
| PULL REORDER_90 | 0.0 | +0.1 [-0.1, +0.3] | +0.13 M [+0.09, +0.17] |

The effect is small because PULL rarely sold short once ADR 0028 was in place, except under
ON_DEMAND, where the limit is waste supply, not the backlog (ADR 0028).
