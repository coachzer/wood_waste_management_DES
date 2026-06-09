# Entity status is persisted as the enum name string, not the auto() int

Date: 2026-06-09
Status: accepted

## Context

`EntityStatus` uses `auto()`, so `.value` is a bare int (1/2/3) determined by declaration
order. `WasteMonitor` serialized `status.value` into every run JSON, and the status-timeline
visualization hardcoded `1 -> OPERATIONAL/green, 2 -> FAILED/red, 3 -> RECOVERING/orange`.
Reordering or inserting an `EntityStatus` member would silently remap every historical run's
status labels and colors with no error — a works-by-accident coupling between enum
declaration order and a viz color map, across the serialization boundary (VIZ-REVIEW T18b).

## Decision

Persist `status.name` (the string `"OPERATIONAL"` / `"FAILED"` / `"RECOVERING"`) everywhere
`WasteMonitor` records status. The visualization maps key on those strings only; the int
branches are deleted.

## Consequences

- Run-JSON schema change: `status` lists now hold strings instead of ints. Simulation
  behavior and all KPIs are unchanged; only the serialized representation moved.
- Run JSONs written before this date carry int statuses and would render as
  `UNKNOWN_*`/gray in the status timeline; regenerate rather than special-case them.
- Enum members can be reordered or extended without corrupting historical labels.
