# Collectors serve the largest treatment order first

Date: 2026-11-18
Status: accepted

## Context

A PULL collector has 3 vehicles. It served signals in posting order, which is code order, with
yesterday's signals ahead of today's. On seed 1, REORDER_90, col_gorenjska spent 147 trips on
02 01 07 (mean 0.23 m3) and 100 on 03 01 01 (mean 0.02 m3). Its 03 01 05 orders went unserved on
181 of 231 ticks (agy, `.scratch/agy-needs/REPORT.md`).

Treatment posts the full gap to its order-up-to level every tick, and signals live a day. So the
bus can hold yesterday's unserved order and today's order for the same operator and type, each
asking for the same gap.

## Decision

`CollectorCompany._signals_in_dispatch_order` orders the signals before dispatch:

- Treatment signals come before other signals.
- Within each group, the largest volume comes first.
- Only the newest treatment signal per (operator, waste type) is live. Older ones are acknowledged
  and dropped. Summing them would order the same gap twice.

PUSH collectors never process signals, so PUSH is unchanged (all 30 PUSH runs byte-identical).

## Consequences

PULL service, seeds 1-2, with generator storage triggers still on: 100% in every strategy, up from
82-94%. Collection rate is 41-62%, because generator triggers still push waste that no operator
ordered. ADR 0032 removes those triggers.
