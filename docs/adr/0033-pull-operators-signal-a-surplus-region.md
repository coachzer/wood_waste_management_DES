# PULL operators signal a surplus region

Date: 2026-11-18
Status: accepted

## Context

After ADRs 0031 and 0032, PULL still fell short only under ON_DEMAND (99.34% service, seeds 1-10).
A treatment operator's order reached only its own region's collector. When the region held too
little of the ordered waste type, the order went unfilled even if another region had stock.

ADR 0032 named the fix (agy's Fix B) and did not adopt it, because the operator has to know the
generator stock of every region. The user chose to add it.

## Decision

`TreatmentOperator._propagate_signal_to_collectors` still signals its own region's PULL collectors
for the full order. It then compares the order with local stock of that waste type (local
collection centers plus local generators). If the order is larger, it also signals the PULL
collectors of the one other region whose generators hold the most of that type, for the deficit
only. That collector collects into its own center, and the operator draws from it through the
existing cross-region fallback.

This is an information assumption: operators see generator stock nationwide. Real buyers know
their main suppliers by region, not exact stock, so this overstates what PULL can coordinate.

The probe version signalled the full order to the surplus region. This version signals the
deficit, so the two regions do not both fill the same gap.

PUSH is unchanged (all 30 PUSH runs byte-identical, seeds 1-10).

## Consequences

Seeds 1-10, Baseline, PULL after minus before (paired, 95% CI):

| Strategy | Service, pts | Uncollected, m3 | Collection transport cost, model currency |
|---|---|---|---|
| ON_DEMAND | +0.60 [+0.38, +0.82] | -4,079 | -9,222 |
| REORDER_50 | 0.00 | -5,801 | -11,670 |
| REORDER_90 | 0.00 | -4,717 | -17,185 |

- PULL ON_DEMAND serves 99.94%, and the REORDER strategies stay at 100%.
- Collection rate moves by at most 0.13 points. PULL still collects about 13% of generation.
- Treatment-anchored bullwhip falls (-0.89 ON_DEMAND, -0.19 REORDER_90). Collector-anchored and
  collector-stage bullwhip rise by 2-3 and 0.6-0.75. Those collector metrics are still unvalidated.
- The lower collection transport cost is not explained. It does not come from more unpriced
  movement: the share of treatment intake drained from another region's collector through
  `_collect_with_fallback`, with no transport cost, time or emissions, is 72.0% before and 72.3%
  after on seed 1 PULL ON_DEMAND (`.scratch/fixb-mfa/`). That unpriced drain predates this ADR and
  is open (`.scratch/fixb-mfa/ISSUE-unpriced-fallback-drain.md`).
