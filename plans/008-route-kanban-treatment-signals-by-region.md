# Plan 008: Route treatment kanban signals to their intended region

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 75c01d9..HEAD -- core/kanban_manager.py core/collector.py core/treatment.py`
> If any of those files changed since this plan was written, compare the
> "Current state" excerpts below against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED (changes PULL-mode behavior; PUSH and flow-based metrics unaffected — see "Why this matters")
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `75c01d9`, 2026-06-11

## Why this matters

In PULL mode, every entity shares **one** `KanbanManager` instance (created in
`core/simulation_manager.py:47`, passed to all collectors, generators, and
treatment operators via `FacilityBuilder`). When a treatment operator needs
waste, it posts a `source_type="treatment"` signal onto this shared bus,
intending it for collectors **in its own region** (`_propagate_signal_to_collectors`
filters to same-region collectors before posting).

But the bus is shared and unaddressed: every PULL collector reads every
non-market signal each tick (`core/collector.py:408-411`). Whichever collector
wakes first wins the race. A collector from the wrong region reads the treatment
signal, finds no local generator holding that waste type, propagates the demand
to *its own* (wrong-region) generators, and then **acknowledges (permanently
consumes) the signal** (`core/collector.py:471`). The intended region's
collector never sees it. This is documented as a known loss path in
`docs/adr/0018-kanban-signal-bus-investigation.md`.

This plan stamps each treatment signal with its `target_region` and makes
collectors skip signals addressed to a different region. The intended
collector then reliably receives the demand and collects from its local
generators. The effect is confined to PULL mode (PUSH ignores kanban entirely).
Flow-based metrics (bullwhip, service level) are unaffected — they measure
physical flows and consumption events, not signal propagation (ADR 0018).

**Scope decision (important — do not expand):** there is exactly **one
collector per region** in this model (verified: each `data/regions/*.json` has a
single collector entry). Region routing therefore fully closes the race — once a
treatment signal is addressed to region R, only region R's single collector can
touch it. The "ack-only-when-fulfilled" variant discussed in the originating
note is **deliberately NOT implemented here**: with one collector per region
there is no intra-region race to guard against, and leaving the signal unacked
after the collector already propagated upstream would re-propagate to generators
every tick (the propagation timestamp changes each tick, defeating
`add_signal`'s dedup) — signal spam, not a fix. The existing no-vehicle path
already retries correctly by breaking without acking (`core/collector.py:464-465`).

## Current state

Three files, each with the exact code as it exists at commit `75c01d9`:

### `core/kanban_manager.py` — the shared signal bus

`add_signal` builds the signal dict; it has no notion of a target region
(lines 11-23):

```python
    def add_signal(self, waste_type, timestamp, volume=0, source_id=None, source_type=None):
        signal_id = f"{source_id}_{waste_type}_{timestamp}"

        # Avoid duplicate signals
        if signal_id not in self.acknowledged_signals:
            self.signals.append({
                'id': signal_id,
                'waste_type': waste_type,
                'timestamp': timestamp,
                'volume': volume,
                'source_id': source_id,
                "source_type": source_type
            })
```

`get_signals` returns all non-acknowledged, non-expired signals — no addressing
(lines 38-42). Stale signals expire after `KANBAN_SIGNAL_MAX_AGE_DAYS` via
`clean_old_signals`.

### `core/treatment.py` — where treatment posts to collectors

`_propagate_signal_to_collectors` (lines 254-277) already filters to same-region
PULL collectors, then posts the signal **without** a target region:

```python
    def _propagate_signal_to_collectors(self, waste_type, needed_volume, current_time):
        """Propagate signals to collectors with availability checking"""
        state = self.state

        local_collectors = [
            c for c in state.collectors 
            if (c.region_type == self.region_type and 
                c.inventory_policy.is_pull() and
                c.availability and 
                c.collection_center.current_storage.get(waste_type, 0) > 0) 
        ]

        for collector in local_collectors:
            available_volume = collector.collection_center.current_storage.get(waste_type, 0)
            signal_volume = min(needed_volume, available_volume)

            if signal_volume > 0:
                collector.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=signal_volume,
                    source_id=self.name,
                    source_type="treatment"
                )
```

`self.region_type` here is a `RegionType` enum (set at `core/treatment.py:91`).
All `local_collectors` are same-region as `self`, so `self.region_type` is the
unambiguous target.

### `core/collector.py` — where collectors read and consume signals

The read filter (lines 408-411) drops only market signals — every other signal
on the shared bus is read regardless of region:

```python
            kanban_signals = [
                s for s in self.kanban_manager.get_signals(self.env.now)
                if s.get('source_type') != "market"
            ]
```

`_process_kanban_signals` (lines 418-471) iterates the signals. The top of the
loop already has a `source_type == "market"` skip (lines 425-426). The
unconditional-ack-on-no-match is the bug (lines 466-471):

```python
            if matching_generators:
                for generator in matching_generators:
                    if self._find_available_vehicle():
                        self.collect_from_generator(generator, requested_volume=signal.get('volume'))

                        self.kanban_manager.acknowledge_signal(signal['id'])
                        break
                    else:
                        break
            else:
                if source_type == "treatment":
                    self._propagate_signal_to_generators(signal, current_time)

                # Acknowledge the signal to prevent it from staying active forever
                self.kanban_manager.acknowledge_signal(signal['id'])
```

`self.region_type` on a collector is a `RegionType` enum (`core/collector.py:100`).
`RegionType` is imported at `core/collector.py:15`.

### Repo conventions that apply

- **Reproducibility (CLAUDE.md "Known Failure Modes")**: a given seed must
  produce byte-identical run JSONs across process invocations. The changes here
  add one dict key and one early-`continue` filter — neither iterates a
  set-of-enums nor changes ordering, so determinism is preserved. The
  `tests/test_determinism.py` gate (Step 4) confirms this.
- **No magic numbers / verbose names** (CLAUDE.md "Key Conventions"): use the
  full name `target_region`, not an abbreviation.
- **Surgical changes**: touch only the three files in scope; do not refactor
  adjacent code.
- **Test pattern**: unit tests that exercise a collector method without a full
  simulation use a lightweight stand-in object and call the method unbound —
  see `tests/core/test_collection_center_storage.py` (its `FakeCollector` /
  `FakeCenter` classes, and the `CollectorCompany._add_to_collection_center(collector, ...)`
  unbound call). Match that style for the new test.
- **Tests are red/blue-team** (project convention): every test must be shown
  non-vacuous — mutate the source to make it fail (red), then restore (green).
  Step 5 does this explicitly.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Run interpreter | `/mnt/c/Python313/python.exe` | the WSL `python3` has no deps — always use this one |
| New test only | `/mnt/c/Python313/python.exe -m pytest tests/core/test_kanban_signal_routing.py -v` | all pass |
| Determinism gate | `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py tests/test_enum_set_ordering.py -q` | all pass |
| Full suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | no new failures vs. baseline |
| Drift check | `git diff --stat 75c01d9..HEAD -- core/kanban_manager.py core/collector.py core/treatment.py` | empty (no drift) |

## Scope

**In scope** (the only files you may modify):
- `core/kanban_manager.py` — add `target_region` param to `add_signal`
- `core/treatment.py` — pass `target_region=self.region_type` in `_propagate_signal_to_collectors`
- `core/collector.py` — add the region filter in `_process_kanban_signals`
- `tests/core/test_kanban_signal_routing.py` — **create** (new test file)
- `docs/adr/0018-kanban-signal-bus-investigation.md` — append a "Superseded in part" note (Step 6); do NOT edit the existing body (ADRs are append-only — CLAUDE.md "Docs & Skills")
- `plans/README.md` — status row + move the backlog bullet (final step)

**Out of scope** (do NOT touch, even though they look related):
- The ack semantics in `core/collector.py:466-471` beyond adding the filter —
  see "Scope decision" in Why this matters. Do not implement
  ack-only-when-fulfilled.
- Generator-sourced signals (`source_type="generator"`) and the
  `collector->collector` / generator signal paths — they have no target region
  and must keep flowing unfiltered (the `source_type=="generator"` match in
  `_process_kanban_signals` already addresses them by `source_id`).
- `_propagate_signal_to_generators` (`core/collector.py:473-493`) — it already
  uses `self.region_type` correctly; leave it.
- Any PUSH-mode path, any flow/metric code, any KPI extraction.

## Git workflow

- Branch: `advisor/008-route-kanban-treatment-signals-by-region`
- Commit per logical unit. Message style (CLAUDE.md "Commits"): imperative verb,
  no colon after the verb, under 72 chars, body explains *why*. Example from
  `git log`: `Parallelize baseline replications and rewrite Pareto figure...`.
  Suggested first commit: `Route treatment kanban signals to their target region`.
- **Do NOT add a `Co-Authored-By` line** (repo owner preference).
- Do NOT push or open a PR — the maintainer pushes themselves.

## Steps

### Step 1: Add `target_region` to `KanbanManager.add_signal`

In `core/kanban_manager.py`, extend the `add_signal` signature with a new
keyword arg `target_region=None` and store it in the signal dict. The new key
must default to `None` so existing callers (generators, collectors propagating
to generators) are unaffected.

Target shape:

```python
    def add_signal(self, waste_type, timestamp, volume=0, source_id=None, source_type=None, target_region=None):
        signal_id = f"{source_id}_{waste_type}_{timestamp}"

        # Avoid duplicate signals
        if signal_id not in self.acknowledged_signals:
            self.signals.append({
                'id': signal_id,
                'waste_type': waste_type,
                'timestamp': timestamp,
                'volume': volume,
                'source_id': source_id,
                "source_type": source_type,
                'target_region': target_region,
            })
```

Note: `target_region` is intentionally **not** part of `signal_id` — addressing
must not change dedup behavior.

**Verify**: `/mnt/c/Python313/python.exe -c "from core.kanban_manager import KanbanManager; km=KanbanManager(); km.add_signal(waste_type='x', timestamp=0, target_region='R'); print(km.signals[0]['target_region'])"`
→ prints `R`

### Step 2: Stamp the target region when treatment posts to collectors

In `core/treatment.py`, in `_propagate_signal_to_collectors`, add
`target_region=self.region_type` to the `add_signal` call:

```python
            if signal_volume > 0:
                collector.kanban_manager.add_signal(
                    waste_type=waste_type,
                    timestamp=current_time,
                    volume=signal_volume,
                    source_id=self.name,
                    source_type="treatment",
                    target_region=self.region_type,
                )
```

**Verify**: `/mnt/c/Python313/python.exe -c "import ast; ast.parse(open('core/treatment.py').read()); print('ok')"`
→ prints `ok`

### Step 3: Filter wrong-region treatment signals in the collector

In `core/collector.py`, in `_process_kanban_signals`, immediately after the
existing market-skip (the `if signal.get('source_type') == "market": continue`
block ending at line 426), add a region filter. Signals with no `target_region`
(generator signals, legacy) are unaddressed and must pass through unchanged:

```python
            # Treatment signals are addressed to one region (the operator's own).
            # The shared bus means every PULL collector reads every signal, so an
            # unaddressed signal could be consumed by the wrong region's collector,
            # which would propagate uselessly and ack it before the intended
            # collector ever sees it (ADR 0018). Skip signals not meant for us;
            # leave them on the bus for the collector they are addressed to.
            target_region = signal.get('target_region')
            if target_region is not None and target_region != self.region_type:
                continue
```

**Verify**: `/mnt/c/Python313/python.exe -c "import ast; ast.parse(open('core/collector.py').read()); print('ok')"`
→ prints `ok`

### Step 4: Confirm determinism and the full suite are still green

**Verify**:
- `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py tests/test_enum_set_ordering.py -q` → all pass
- `/mnt/c/Python313/python.exe -m pytest tests/ -q` → no failures introduced by this change. (If a *pre-existing* failure unrelated to kanban shows up, note it and continue — do not fix out-of-scope failures.)

### Step 5: Write the routing test (and prove it non-vacuous)

Create `tests/core/test_kanban_signal_routing.py`. Model the stand-in style on
`tests/core/test_collection_center_storage.py` (lightweight fake collector,
call the method unbound). The test must assert both directions of the fix:

1. **Wrong-region collector leaves a treatment signal alone**: post a treatment
   signal addressed to region A onto a shared `KanbanManager`; have a collector
   whose `region_type` is region B run `_process_kanban_signals` over the
   non-market signals; assert the signal is **still** returned by
   `get_signals` (i.e. NOT acknowledged).
2. **Right-region collector consumes it**: a collector whose `region_type` is
   region A, with no matching generators (so it takes the propagate-then-ack
   branch), runs `_process_kanban_signals`; assert the signal is afterwards
   **gone** from `get_signals` (acknowledged).
3. **Unaddressed signals still pass through**: a signal with
   `target_region=None` (e.g. a `source_type="generator"` signal) is processed
   by any collector regardless of region — assert it is acted on (acknowledged
   or attempted), confirming the filter does not block legacy signals.

The fake collector needs: `region_type` (a `RegionType`), `kanban_manager`,
`env` (use `types.SimpleNamespace(now=1.0)` — see the timestamp note below),
and stubbed `_get_prioritized_generators()` → `[]`, plus a **stub method**
`_propagate_signal_to_generators(self, signal, current_time)` that does nothing.
That stub is load-bearing: the real method (`core/collector.py:473-493`) reads
`self.state.generators`, which `FakeCollector` does not provide — without the
stub, the right-region test crashes with `AttributeError` on `self.state`. With
no matching generators these stubs are enough; `_find_available_vehicle` and
`collect_from_generator` are never reached. `_process_kanban_signals` itself
touches no other `self.*` attributes (verified against `core/collector.py:418-471`).

**Timestamp note (use `1.0`, not `0.0`):** `KanbanManager.get_signals` only
prunes stale signals when `current_time` is truthy (`if current_time:` at
`core/kanban_manager.py:40`), so `0.0` silently skips pruning. The tests below
don't depend on pruning, but use `timestamp=1.0` / `env.now=1.0` throughout so a
future stale-signal case added to this file behaves as expected. Read the
non-acknowledged signals back with a plain inline comprehension over
`km.get_signals(1.0)` (mirroring the real read at `core/collector.py:408-411`) —
do not add a wrapper helper.

Suggested skeleton (adapt names/imports to what the file actually exposes):

```python
from types import SimpleNamespace

from core.collector import CollectorCompany
from core.kanban_manager import KanbanManager
from models.enums import RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


class FakeCollector:
    """Minimal stand-in for CollectorCompany._process_kanban_signals.

    The method is called unbound -- CollectorCompany._process_kanban_signals(fake, ...)
    -- so self resolves to this FakeCollector and self._propagate_signal_to_generators
    resolves to the stub below (not the real method that needs self.state).
    """

    def __init__(self, region_type, kanban_manager):
        self.region_type = region_type
        self.kanban_manager = kanban_manager
        self.env = SimpleNamespace(now=1.0)

    def _get_prioritized_generators(self):
        return []

    def _propagate_signal_to_generators(self, signal, current_time):
        pass  # stub: the real one reads self.state, which we do not provide


def _pending_non_market(km):
    """Non-acknowledged, non-market signals still on the bus."""
    return [s for s in km.get_signals(1.0) if s.get('source_type') != "market"]


def test_wrong_region_collector_does_not_consume_treatment_signal():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="treatment-A", source_type="treatment",
                  target_region=RegionType.PODRAVSKA)
    wrong = FakeCollector(RegionType.GORENJSKA, km)

    CollectorCompany._process_kanban_signals(wrong, _pending_non_market(km))

    assert len(_pending_non_market(km)) == 1, \
        "wrong-region collector must leave the signal on the bus"


def test_right_region_collector_consumes_treatment_signal():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="treatment-A", source_type="treatment",
                  target_region=RegionType.PODRAVSKA)
    right = FakeCollector(RegionType.PODRAVSKA, km)

    CollectorCompany._process_kanban_signals(right, _pending_non_market(km))

    assert _pending_non_market(km) == [], \
        "right-region collector should propagate upstream and ack"


def test_unaddressed_signal_passes_through_any_region():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="gen-1", source_type="generator")  # target_region defaults to None
    collector = FakeCollector(RegionType.GORENJSKA, km)

    CollectorCompany._process_kanban_signals(collector, _pending_non_market(km))

    assert _pending_non_market(km) == [], \
        "an unaddressed signal must not be blocked by the region filter"
```

`_pending_non_market` is a thin readability helper (one comprehension, used
identically in setup and assertion) — keep it as shown; it is not the confusing
double-evaluation a draft of this plan once contained.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/core/test_kanban_signal_routing.py -v` → 3 passed

**Prove non-vacuous (red/blue)**: temporarily comment out the filter block added
in Step 3, re-run the test, and confirm
`test_wrong_region_collector_does_not_consume_treatment_signal` **fails** (the
wrong-region collector now consumes the signal). Then **restore** the filter and
confirm all 3 pass again. Report both observations in your completion note.

### Step 6: Note the ADR supersession

ADRs are append-only (CLAUDE.md). Do **not** edit the body of
`docs/adr/0018-kanban-signal-bus-investigation.md`. Append a short note at the
end of the file recording that the deferred fix in the "Future work" / "Decision"
section was implemented by this plan — region routing only, ack semantics
unchanged — e.g.:

```markdown
## Addendum 2026-06-11 — signal-loss fix implemented (plan 008)

The deferred cross-region signal-loss fix is now implemented: treatment
signals carry a `target_region` (the operator's own region) and collectors
skip signals addressed to another region (`core/kanban_manager.py`,
`core/treatment.py`, `core/collector.py`). Scoped to routing only — with one
collector per region there is no intra-region race, so ack semantics are
unchanged. Flow-based metrics remain unaffected. Regression:
`tests/core/test_kanban_signal_routing.py`.
```

**Verify**: `git diff --stat docs/adr/0018-kanban-signal-bus-investigation.md`
→ shows only additions (no deletions/modifications to existing lines).

## Test plan

- New file `tests/core/test_kanban_signal_routing.py` with the three cases in
  Step 5: wrong-region skip, right-region consume, unaddressed pass-through.
- Structural pattern: `tests/core/test_collection_center_storage.py` (fake
  collector + unbound method call).
- Non-vacuous proof: Step 5's red/blue mutation of the Step 3 filter.
- Determinism gate: `tests/test_determinism.py` + `tests/test_enum_set_ordering.py`
  must stay green (Step 4).
- Verification: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → no new failures.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `/mnt/c/Python313/python.exe -m pytest tests/core/test_kanban_signal_routing.py -v` → 3 passed
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py tests/test_enum_set_ordering.py -q` → all pass
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` → no failures newly introduced by this change
- [ ] `grep -n "target_region" core/kanban_manager.py core/treatment.py core/collector.py` → at least one match in each file
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `git diff docs/adr/0018-kanban-signal-bus-investigation.md` shows additions only
- [ ] `plans/README.md` status row for 008 updated; backlog bullet moved (final step)

## STOP conditions

Stop and report back (do not improvise) if:

- The drift check shows any in-scope file changed since `75c01d9`, or a
  "Current state" excerpt no longer matches the live code.
- You discover there is **more than one collector per region** (check
  `data/regions/*.json` — each should have exactly one collector). If so, the
  "one collector per region" assumption this plan rests on is false, and
  ack-only-when-fulfilled may genuinely be needed — stop and report rather than
  implementing it.
- The full suite (`tests/ -q`) shows a *new* failure that bisects to this
  change (especially in `tests/test_determinism.py` — that would mean the change
  broke byte-identical reproducibility, which it must not).
- The red/blue mutation in Step 5 does NOT make the wrong-region test fail — that
  means the test isn't actually exercising the filter; fix the test before
  proceeding.
- The fix appears to require touching an out-of-scope file.

## Maintenance notes

For whoever owns this code next:

- **What interacts with this**: if the model ever gains *multiple collectors per
  region*, revisit — region routing no longer uniquely identifies a collector,
  and the intra-region race (and thus ack-only-when-fulfilled) becomes relevant.
  The STOP condition above guards the executor against this today.
- **What a reviewer should scrutinize**: (1) that `target_region` is NOT part of
  `signal_id` (must not change dedup); (2) that the filter uses
  `target_region is not None` so legacy/unaddressed signals still flow; (3) that
  `tests/test_determinism.py` stayed green — the change must keep runs
  byte-identical.
- **Deferred out of this plan (intentionally)**: ack-only-when-fulfilled,
  per-region signal queues (Option C in the originating note), and any
  addressing of generator-sourced signals. Region routing was the minimal
  correct fix given one-collector-per-region; the rest is unjustified scope.
- **Expected KPI effect**: modest, PULL-only. ADR 0018 found kanban's main value
  is *gating* collector behavior, not routing accuracy — the gating is unchanged,
  so aggregate throttling is preserved. If you cite PULL numbers after this lands,
  re-run the baseline; flow-based metrics (bullwhip, service level) should be
  effectively unchanged.
