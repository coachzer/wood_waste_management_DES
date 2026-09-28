# Kanban signal bus is load-bearing but lossy

Status: **accepted**
Date: 2026-06-11

## Context

The simulation uses a single shared `KanbanManager` instance for all
entities (generators, collectors, treatment operators). In PULL mode,
the kanban signal cascade was designed to carry demand upstream:
treatment signals collectors, and collectors signal generators. An item
in the plans README flagged two concerns:

1. **Cross-region signal consumption.** Any collector can read and
   acknowledge any signal on the shared bus, including signals meant
   for a different region's collector.
2. **Unconditional acknowledgment.** When a collector processes a
   treatment signal but finds no matching generators with stock, it
   still acknowledges (consumes) the signal (`collector.py:471`), so no
   other collector ever sees it.

The question was whether the kanban mechanism has any measurable
effect or is dead code.

## Investigation

An A/B test (`tests/test_kanban_effectiveness.py`) compared PULL x
ON_DEMAND with kanban enabled (the default) against kanban disabled
(`propagates_reorder_signals_upstream` and
`should_process_kanban_signals` monkey-patched to return False) across
seeds 42-44.

### Results (seed-averaged)

| KPI                    | Kanban ON | Kanban OFF | Change        |
|------------------------|-----------|------------|---------------|
| Service level (full)   | ~57%      | ~71%       | OFF +14 pp    |
| Total collected (m3)   | ~1.1M     | ~1.6M      | OFF +48%      |
| Landfill volume (m3)   | ~66K      | ~186K      | OFF +182%     |
| Emissions (kgCO2e)     | ~17M      | ~46M       | OFF +170%     |
| System cost            | ~16M      | ~26M       | OFF +60%      |

The higher service level with kanban OFF is misleading. It comes from
collectors over-collecting every cycle (falling through to
`_unified_collection_strategy` at `collector.py:416`), which floods the
system with more waste than treatment can process, so the excess is
landfilled. Emissions and costs roughly triple.

## Decision

**The kanban signal bus is load-bearing.** Its main effect is not
"priming upstream supply" but **gating collector behavior**. When
`should_process_kanban_signals` returns True and signals are pending,
the PULL collector processes only those signals instead of collecting
greedily by volume. This throttling is what makes PULL actually
pull-driven.

The signal-loss bug (cross-region unconditional ack) remains. It
probably lowers PULL efficiency, since some upstream cascade signals are
consumed without useful work, but the gating mechanism is clearly
essential. We document the loss path but do not fix it in this
investigation. A fix would change the shared bus's semantics and needs
careful design (per-region queues, targeted signal routing, or
ack-only-if-served).

## Consequences

- **Keep the kanban mechanism in place.** It is not dead code, and
  removing or bypassing it changes results as shown above.
- **Paper claims about PULL signal latency should mention the lossy
  cascade.** Because of the signal-loss path, collectors that cannot
  fulfill some upstream demand signals still consume them.
- **Flow-based metrics (bullwhip, service level) are unaffected** by
  signal loss, because they measure physical flows and consumption
  events, not signal propagation.
- **Future work.** If PULL efficiency matters for a paper claim,
  scope a fix for the unconditional ack at `collector.py:471` (e.g.,
  ack only when the collector actually collected, or re-queue the
  signal). Track it as a separate issue.

## Addendum 2026-06-11: signal-loss fix implemented (plan 008)

The deferred cross-region signal-loss fix is now implemented. Treatment
signals carry a `target_region` (the operator's own region), and
collectors skip signals addressed to another region
(`core/kanban_manager.py`, `core/treatment.py`, `core/collector.py`).
The fix covers routing only. With one collector per region there is no
race within a region, so ack semantics are unchanged. Flow-based metrics
remain unaffected. Regression test:
`tests/core/test_kanban_signal_routing.py`.
