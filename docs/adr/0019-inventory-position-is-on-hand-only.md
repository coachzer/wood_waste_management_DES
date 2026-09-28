# Reorder decisions use on-hand stock only, and in-transit volume is excluded

Date: 2026-06-11
Status: accepted

## Context

Every reorder decision in the simulation, at treatment, collector or generator, reads the on-hand
storage level at the moment of the check. No echelon counts the volume already in transit from an
upstream replenishment that was requested but has not arrived. This convention is deliberately narrower
than the classical one. The classical inventory position is on-hand + in-transit − backorders
(Silver, Pyke & Peterson 1998). This model uses on-hand only.

The consequence shows most clearly under long transport lead times. In the SupplyDisruption scenario
(`trans_time = (4.0, 1.2)`, mean 4.0 days, std 1.2; `config/base_config.py:115`), a reorder check that
fires on day 1 cannot see the replenishment order placed on day 0 that is still in transit. If the
on-hand level is still below the reorder threshold when the day-2 check runs, a second order is placed,
and so on. Several orders stack in the pipeline without the ordering echelon knowing, and when the first
batch lands, the level overshoots. This stacking and overshoot interacts directly with lead-time length.
Chen et al. (2000) show that bullwhip amplification grows with both the mean and the variance of lead
time ("Quantifying the bullwhip effect in a simple supply chain", *Management Science* 46(3), 436-443).
The on-hand-only convention therefore amplifies that effect under the longer transport parameters of
SupplyDisruption compared with the Baseline scenario.

The effect is strongest under PULL × REORDER_90. The reorder threshold is high (90% of capacity), so
orders fire often, and none of them knows about the pipeline already building upstream.

## Decision

Reorder checks at every echelon read on-hand stock only. No echelon keeps or reads an in-transit ledger
for replenishment decisions.

**Treatment** (`core/treatment.py:197-200`):

```python
current_total = sum(self.waste_storage.values())
return self.stock_strategy_behavior.treatment_should_reorder(
    current_total, self.waste_storage_capacity
)
```

`self.waste_storage` is the on-hand dict, and `current_total` is its sum. There is no in-transit term.

**Collector** (`core/collector.py:714-719`):

```python
def _calculate_utilization(self) -> float:
    storage_dict = self.collection_center.current_storage
    total_capacity = self.collection_center.waste_storage_capacity
    return (
        sum(storage_dict.values()) / total_capacity if total_capacity > 0 else 0.0
    )
```

`collection_center.current_storage` is the on-hand dict. The utilization ratio is the only input to the
volume-driven collection threshold check. `active_transports` exists on the collector, but no reorder
path reads it.

**The sender's stock drops immediately.** When a collector dispatches waste to treatment via
`transfer_waste_to_region`, the sender's storage is decremented when the transport is requested, before
it completes (`core/collector.py:539-540`):

```python
# Remove from our storage immediately (it's now "in transit")
self.collection_center.current_storage[waste_type] -= volume
```

So the sender's on-hand balance already reflects the dispatch. The receiving echelon cannot see that
in-transit volume, because it reads only its own on-hand.

**The order-up-to level `S = waste_storage_capacity`** (order the gap to full) is documented in the
Stock Strategy entry of CONTEXT.md and is not repeated here.

**Collector volume-driven thresholds** (`core/strategies/inventory_policy.py:83, 122`):

- PUSH collectors trigger collection when `utilization < push_threshold`, where
  `push_threshold = min(0.80, adaptive_threshold + 0.10)`.
- PULL collectors that fall back to volume-driven collection trigger when
  `utilization < pull_threshold`, where `pull_threshold = max(0.15, adaptive_threshold - 0.15)`.

The stock-strategy object supplies `adaptive_threshold`. REORDER_50 returns 0.50 (PUSH threshold 0.60,
PULL threshold 0.35). REORDER_90 returns 0.90 (PUSH threshold capped at 0.80, PULL threshold 0.75).
ON_DEMAND returns a value that ramps with time, `0.10 + min(0.30, base_time × 0.001)`, from 0.10 at
t = 0 to 0.40 at t ≥ 300 days (PUSH threshold up to 0.50, PULL threshold up to 0.25). In every case the
threshold is compared with the on-hand utilization from `_calculate_utilization`.

Classical inventory position (on-hand + in-transit − backorders) is **future work**.

## Consequences

- Under short lead times (Baseline: `trans_time = (1.35, 0.1)`), the on-hand-only convention is nearly
  indistinguishable from full inventory position, because in-transit volume lands before the next
  reorder check fires.
- Under long, variable lead times (SupplyDisruption: `trans_time = (4.0, 1.2)`), several replenishment
  orders can stack before the first arrives, which produces overshoot when they land. This is an
  expected modeling artifact, stated as a manuscript footnote (see `config/base_config.py:105-110`).
- Read bullwhip amplification under SupplyDisruption knowing that this convention inflates order
  variance compared with a model that tracks pipeline inventory (Chen et al. 2000). The comparison
  across policies (PUSH vs PULL) stays internally consistent, because the same convention applies to
  all six policy × strategy configurations.
- The omission matters little for the Baseline and GenerationSurge scenarios but becomes a material
  modeling assumption in SupplyDisruption. Papers that use SupplyDisruption bullwhip numbers must
  acknowledge it in the limitations section.
- Full inventory position would need each ordering echelon to keep a running tally of in-transit
  volume by waste type, incremented at dispatch and decremented at receipt. That is a non-trivial
  change to the collector and treatment reorder logic.

## References

- Chen, F., Drezner, Z., Ryan, J. K., & Simchi-Levi, D. (2000). Quantifying the bullwhip effect in a
  simple supply chain: The impact of forecasting, lead times, and information. *Management Science*,
  46(3), 436-443.
- `config/base_config.py:105-110`: inline note on the stacking behavior in SupplyDisruption.
- CONTEXT.md "Stock Strategy" entry: the S = waste_storage_capacity order-up-to level.
- CONTEXT.md "Throughput Bullwhip" entry: CV² normalization and echelon definitions (ADR 0004 et seq.).
