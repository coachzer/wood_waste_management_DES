# ADR 0018 -- Kanban signal bus is load-bearing but lossy

Status: **accepted**
Date: 2026-06-11

## Context

The simulation uses a single shared `KanbanManager` instance for all
entities (generators, collectors, treatment operators). In PULL mode,
the kanban signal cascade was designed to propagate demand upstream:
treatment signals collectors, collectors signal generators. A plans
README item flagged two concerns:

1. **Cross-region signal consumption**: any collector can read and
   acknowledge any signal on the shared bus, even signals intended for
   a different region's collector.
2. **Unconditional acknowledgment**: when a collector processes a
   treatment signal but finds no matching generators with stock, it
   still acknowledges (consumes) the signal (`collector.py:471`),
   preventing other collectors from ever seeing it.

The question was whether the kanban mechanism has any measurable
effect, or is dead code.

## Investigation

An A/B test (`tests/test_kanban_effectiveness.py`) compared PULL x
ON_DEMAND with kanban enabled (default) vs. disabled (monkey-patched
`propagates_reorder_signals_upstream` and
`should_process_kanban_signals` to return False) across seeds 42-44.

### Results (seed-averaged)

| KPI                    | Kanban ON | Kanban OFF | Change        |
|------------------------|-----------|------------|---------------|
| Service level (full)   | ~57%      | ~71%       | OFF +14 pp    |
| Total collected (m3)   | ~1.1M     | ~1.6M      | OFF +48%      |
| Landfill volume (m3)   | ~66K      | ~186K      | OFF +182%     |
| Emissions (kgCO2e)     | ~17M      | ~46M       | OFF +170%     |
| System cost            | ~16M      | ~26M       | OFF +60%      |

Higher service level with kanban OFF is misleading: it comes from
collectors greedily over-collecting every cycle (falling through to
`_unified_collection_strategy` at `collector.py:416`), flooding the
system with waste that overwhelms treatment capacity and gets
landfilled. Emissions and costs roughly triple.

## Decision

**The kanban signal bus is load-bearing.** Its primary effect is not
"priming upstream supply" but **gating collector behavior**: when
`should_process_kanban_signals` returns True with pending signals,
the PULL collector processes only those signals instead of
volume-driven greedy collection. This throttling is what makes PULL
actually pull-driven.

The signal-loss bug (cross-region unconditional ack) remains. It
likely degrades PULL efficiency (some upstream cascade signals are
consumed without useful work), but the gating mechanism is clearly
essential. We document the loss path but do not fix it in this
investigation -- a fix would change the shared bus's semantics and
requires careful design (per-region queues, targeted signal routing,
or ack-only-if-served).

## Consequences

- **Do not remove or bypass the kanban mechanism.** It is not dead
  code.
- **Paper claims about PULL signal latency should note the lossy
  cascade.** The signal-loss path means some upstream demand signals
  are consumed by collectors that cannot fulfill them.
- **Flow-based metrics (bullwhip, service level) are unaffected** by
  signal loss -- they measure physical flows and consumption events,
  not signal propagation.
- **Future work**: if PULL efficiency matters for a paper claim,
  scope a fix for the unconditional ack at `collector.py:471` (e.g.,
  ack only when the collector actually collected, or re-queue the
  signal). Track as a separate issue.

## Addendum 2026-06-11 -- signal-loss fix implemented (plan 008)

The deferred cross-region signal-loss fix is now implemented: treatment
signals carry a `target_region` (the operator's own region) and collectors
skip signals addressed to another region (`core/kanban_manager.py`,
`core/treatment.py`, `core/collector.py`). Scoped to routing only -- with one
collector per region there is no intra-region race, so ack semantics are
unchanged. Flow-based metrics remain unaffected. Regression:
`tests/core/test_kanban_signal_routing.py`.
