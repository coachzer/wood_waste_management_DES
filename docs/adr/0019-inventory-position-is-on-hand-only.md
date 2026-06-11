# 0019 — Reorder decisions use on-hand stock only; in-transit volume is excluded

Date: 2026-06-11
Status: accepted

## Context

Every reorder decision in the simulation — whether at treatment, collector, or generator — reads the
on-hand storage level at the moment of the check. No echelon accounts for the volume already in transit
from an upstream replenishment that has been requested but not yet received. This is a deliberate,
narrower-than-classical convention: the classical inventory position is on-hand + in-transit − backorders
(Silver, Pyke & Peterson 1998); this model uses on-hand only.

The consequence is visible most sharply under long transport lead times. In the SupplyDisruption scenario
(`trans_time = (4.0, 1.2)`, mean 4.0 days, std 1.2; `config/base_config.py:115`), a reorder check
that fires on day 1 cannot "see" the replenishment order placed on day 0 still in transit. If the
on-hand level remains below the reorder threshold when the day-2 check runs, a second order is placed —
and so on. Multiple orders stack in the pipeline unbeknownst to the ordering echelon; when the first
batch lands, the level overshoots. This stacking-and-overshoot mechanism is a direct interaction with
lead-time length: Chen et al. (2000) show that bullwhip amplification grows with both the mean and
variance of lead time ("Quantifying the bullwhip effect in a simple supply chain", *Management Science*
46(3), 436-443), so the on-hand-only convention amplifies that effect under the stretched transport
parameters of SupplyDisruption relative to the Baseline scenario.

The effect is sharpest under PULL × REORDER_90, where the reorder threshold is high (90% of capacity)
so orders fire frequently, each one unaware of the pipeline already accumulating upstream.

## Decision

Reorder checks at every echelon read on-hand stock only. No echelon maintains or reads an in-transit
ledger for replenishment decisions.

**Treatment** (`core/treatment.py:197-200`):

```python
current_total = sum(self.waste_storage.values())
return self.stock_strategy_behavior.treatment_should_reorder(
    current_total, self.waste_storage_capacity
)
```

`self.waste_storage` is the on-hand dict; `current_total` is its sum. No in-transit term.

**Collector** (`core/collector.py:714-719`):

```python
def _calculate_utilization(self) -> float:
    storage_dict = self.collection_center.current_storage
    total_capacity = self.collection_center.waste_storage_capacity
    return (
        sum(storage_dict.values()) / total_capacity if total_capacity > 0 else 0.0
    )
```

`collection_center.current_storage` is the on-hand dict. The utilization ratio is the sole input to
the volume-driven collection threshold check. `active_transports` exists on the collector but no
reorder path reads it.

**In-transit decrement is immediate**: when a collector dispatches waste to treatment via
`transfer_waste_to_region`, the sender's storage is decremented at transport-request time before the
transport completes (`core/collector.py:539-540`):

```python
# Remove from our storage immediately (it's now "in transit")
self.collection_center.current_storage[waste_type] -= volume
```

So the sender's on-hand balance already reflects the dispatch. The receiving echelon, however, has no
visibility into that in-transit volume; it reads only its own on-hand.

**The order-up-to level `S = waste_storage_capacity`** (gap-to-full order quantity) is documented in
the Stock Strategy entry of CONTEXT.md and is not repeated here.

**Collector volume-driven thresholds** (`core/strategies/inventory_policy.py:83, 122`):

- PUSH collectors trigger collection when `utilization < push_threshold`, where
  `push_threshold = min(0.80, adaptive_threshold + 0.10)`.
- PULL collectors falling back to volume-driven collection trigger when
  `utilization < pull_threshold`, where `pull_threshold = max(0.15, adaptive_threshold - 0.15)`.

`adaptive_threshold` is supplied by the stock-strategy object: REORDER_50 returns 0.50 (PUSH threshold
0.60, PULL threshold 0.35); REORDER_90 returns 0.90 (PUSH threshold capped to 0.80, PULL threshold
0.75); ON_DEMAND returns a time-ramped value `0.10 + min(0.30, base_time × 0.001)`, ranging from 0.10
at t = 0 to 0.40 at t ≥ 300 days (PUSH threshold up to 0.50, PULL threshold up to 0.25). In all
cases the threshold is computed on the on-hand utilization from `_calculate_utilization`.

Classical inventory position (on-hand + in-transit − backorders) is **future work**.

## Consequences

- Under short lead times (Baseline: `trans_time = (1.35, 0.1)`) the on-hand-only convention is nearly
  indistinguishable from full inventory position: lead times are short enough that in-transit volume
  lands before the next reorder check fires.
- Under long, variable lead times (SupplyDisruption: `trans_time = (4.0, 1.2)`) multiple replenishment
  orders can stack before the first arrives, producing overshoot on landing. This is an expected
  modeling artifact, stated as a manuscript footnote (see `config/base_config.py:105-110`).
- Bullwhip amplification under SupplyDisruption should be interpreted with the awareness that the
  convention inflates order variance relative to a model that tracks pipeline inventory (Chen et al.
  2000). The comparison across policies (PUSH vs PULL) remains internally consistent because the same
  convention applies to all six policy × strategy configurations.
- The omission is architecturally minor for the Baseline and GenerationSurge scenarios but becomes a
  material modeling assumption in SupplyDisruption. Papers drawing on SupplyDisruption bullwhip numbers
  must acknowledge this in the limitations section.
- Implementing full inventory position would require each ordering echelon to maintain a running tally
  of in-transit volumes keyed by waste type, updated at dispatch and decremented at receipt — a
  non-trivial change to the collector and treatment reorder logic.

## References

- Chen, F., Drezner, Z., Ryan, J. K., & Simchi-Levi, D. (2000). Quantifying the bullwhip effect in a
  simple supply chain: The impact of forecasting, lead times, and information. *Management Science*,
  46(3), 436-443.
- `config/base_config.py:105-110` — inline note on the stacking behavior in SupplyDisruption.
- CONTEXT.md "Stock Strategy" entry — S = waste_storage_capacity order-up-to level.
- CONTEXT.md "Throughput Bullwhip" entry — CV² normalization, echelon definitions (ADR 0004 et seq.).
