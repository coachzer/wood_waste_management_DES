# PULL collectors stop servicing signals at the utilization ceiling

Date: 2026-11-18
Status: accepted

## Context

ADR 0021 raised PULL service and left PULL landfill higher, with the cause unconfirmed. All PULL
landfill was at collection centers. PUSH had none.

`PullPolicy.collector_should_collect` returned `True` whenever a non-market signal was on the bus,
whatever the collection center's utilization. PUSH collectors stop at `min(0.80, threshold + 0.10)`.
A PULL collector with a full center kept collecting, and the excess went to landfill or paid for
storage expansion.

Two other explanations were tested first and refuted (10 seeds, CRN, 95% paired-t intervals):
reserving in-flight capacity at dispatch, and gating cross-region repositioning on the destination's
free space. Neither reduced landfill. Details and the probe code are in
`.scratch/pushpull-followups/issues/01-pull-landfill-increase-after-adr-0021.md`.

## Decision

A PULL collector services pending signals only while its collection center is below
`COLLECTOR_UTILIZATION_CEILING = 0.80`. Without pending signals it keeps its lower PULL threshold.
PUSH now reads the same constant for its existing 0.80 cap, so its behaviour is unchanged.

The signal read still happens before the ceiling check. When this ADR was written,
`KanbanManager.get_signals` pruned the bus as it read, so the order mattered. Reads have since become
pure (pruning moved to `add_signal`), and the order no longer affects results.

## Consequences

Paired over seeds 1-10, PULL after minus PULL before (95% interval):

| Strategy | Landfill, m3/year | Full service, points | Collection rate, points | Collector bullwhip |
|---|---|---|---|---|
| ON_DEMAND | -13,854 [-17,289, -10,418] | -0.11 [-0.92, +0.69] | -1.89 [-2.10, -1.68] | +33 [+15, +51] |
| REORDER_50 | -14,558 [-18,691, -10,425] | -0.12 [-0.55, +0.32] | -2.64 [-3.24, -2.04] | +40 [+31, +49] |
| REORDER_90 | -32,399 [-37,763, -27,034] | -0.53 [-1.08, +0.02] | -3.09 [-3.53, -2.65] | +46 [+25, +67] |

- **PULL landfill falls to zero on every seed.** Every m3 of it came from signals forcing collection
  into centers at or above 80% utilization. Storage-overflow and expansion costs fall with it.
- **The waste stays at generators instead.** Collection rate falls by 1.9 to 3.1 points. Generator
  landfill stays at about 0 m3. Armed mass-balance checks pass for all three PULL strategies (seed 1).
- **Full service does not change detectably.** REORDER_90 is borderline: its upper bound is +0.02,
  so a small loss of up to about one point cannot be ruled out.
- **Collector bullwhip rises** in all three strategies. Treatment bullwhip changes are within noise.
- **PUSH is unchanged.** Seed-1 KPIs are identical for all three strategies.
- Part of ADR 0021's threshold confound is gone, since both policies now share the 0.80 cap. The
  lower PULL no-signal threshold and the different efficiency curves remain.
