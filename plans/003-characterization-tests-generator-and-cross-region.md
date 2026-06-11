# Plan 003: Pin generator overflow and cross-region double-count guard with characterization tests

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- core/generator.py core/treatment.py tests/core/`
> If any in-scope source file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1 (must land before Plan 004, which changes generator behavior)
- **Effort**: M
- **Risk**: LOW (tests only — no production code changes)
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

`core/generator.py` (19 commits in 3 months) has zero behavioral tests, and `core/treatment.py`'s cross-region path (38 commits) carries a documented mass-balance invariant — cross-region repositioned waste must NOT be added to `collected_waste` or it double-counts (ADR 0009; a previous real bug) — with no test pinning it. This repo's test standard is adversarial: every test pins a specific failure mode and must be demonstrably non-vacuous (mutate the production code to see red, then restore). These tests are also the safety net required before Plan 004 changes the generator's storage-cap behavior.

## Current state

### Files

- `core/generator.py` — `WasteGenerator`; the methods to pin are `_generate_waste_for_period` (line 247), `_update_waste_stream` (line 191), `_handle_overflow` (line 211).
- `core/treatment.py` — `TreatmentOperator`; the methods to pin are `_collect_from_cross_region` (line 560) and its caller `request_waste_directly` (line 522).
- `tests/core/test_collection_center_storage.py` — THE structural exemplar: drives a collector method over `SimpleNamespace`/fake-class stubs with no SimPy environment, asserting mass conservation. Read it fully before writing anything.
- `tests/core/test_treatment_flow_logging.py` — second exemplar for stubbing treatment-side collaborators.
- `tests/core/conftest.py` — shared fixtures; check what it provides before duplicating stubs.

### Behavior to pin, generator side (`core/generator.py:247-269`)

```python
    def _generate_waste_for_period(self, seasonal_factor, current_time):
        """Generate waste for all waste types in one period with efficiency consideration"""
        if self.uncertainty_set:
            if self.status == EntityStatus.FAILED:
                return

        available_storage = self.waste_storage_capacity - self.current_storage
        daily_factors = self._calculate_daily_factors()

        for (waste_type, base_rate), daily_factor in zip(
            self.waste_generation_rates.items(), daily_factors
        ):
            potential_volume = base_rate * seasonal_factor * daily_factor * self.efficiency

            # Record the source-offered volume before the storage cap (ADR 0005
            # floor), accumulated for every waste type and consuming no RNG.
            self.total_potential_generated[waste_type] += potential_volume

            if potential_volume <= available_storage:
                self._update_waste_stream(
                    waste_type, potential_volume, current_time, self.history_index
                )
                available_storage -= potential_volume
```

Key facts to characterize AS-IS (Plan 004 will then change one of them deliberately):

1. `total_potential_generated[waste_type]` accrues the full potential volume for EVERY type, even when nothing is stored (the ADR 0005 source-variance floor — must stay policy-invariant).
2. When `potential_volume > available_storage`, the type generates NOTHING (all-or-nothing drop, not a partial fill). `total_generated` and `current_storage` are unchanged for that type.
3. When it fits, `_update_waste_stream` adds to `waste_streams[waste_type].volume`, `current_storage`, `total_generated[waste_type]`, and calls `self.state.track_add_waste(self.region, waste_type, generated_volume)`.

`_handle_overflow` (`core/generator.py:211` onward) — when total stream volume exceeds capacity it calls `handle_storage_event(self, split_overflow_by_type(...), force_landfill=...)`, re-reads `self.waste_storage_capacity` (which may have expanded inside the call), then scales all streams down to the effective capacity, calling `state.track_remove_waste` for each reduction. The invariant: after `_handle_overflow`, `current_storage <= waste_storage_capacity` and every removed m³ was reported via `track_remove_waste` (mass is either kept or explicitly removed — nothing silently vanishes).

### Behavior to pin, treatment side (`core/treatment.py:560-590`)

```python
    def _collect_from_cross_region(self, amount_to_collect: float, waste_types: List[WasteType], collected_waste: dict) -> float:
        """Reposition waste from cross-region collectors via transport.

        A collector-to-collector repositioning move (ADR 0009): waste is removed
        from the remote collector and routed to a collector in this region, where
        it lands in the collection center and later reaches treatment via the local
        intake path (``provide_waste_for_treatment``). It is therefore NOT added to
        ``collected_waste`` here -- doing so would double-count it in the waste-side
        mass balance. The volume still satisfies the cross-region portion of the
        request (deducted from ``remaining``) but reaches treatment only on the
        later local pickup.
        """
        if amount_to_collect <= 0: return 0.0

        state = self.state
        remote_collectors = [c for c in state.collectors if c.region_type != self.region_type and c.availability]
        remote_collectors.sort(key=lambda c: get_distance(self.region_type, c.region_type))

        remaining = amount_to_collect
        for collector in remote_collectors[:3]:
            if remaining <= 0: break

            transport_collected = self._request_via_transport(collector, remaining, waste_types)
            for waste_type, amount in transport_collected.items():
                remaining -= amount
        return remaining
```

Invariants to pin: (a) `collected_waste` is NOT mutated by this method, no matter what `_request_via_transport` returns; (b) the return value is `amount_to_collect` minus the transported volume; (c) only the 3 nearest remote collectors are consulted; (d) same-region collectors are never consulted.

`get_distance` comes from `models/distances.py::get_distance(region_a, region_b)` and takes `RegionType` values — your stub collectors need real `RegionType` enum members (see `models/enums.py`) so sorting works without monkeypatching.

### Conventions

- Tests stub collaborators with `SimpleNamespace` or tiny fake classes and call methods **unbound or on a hand-built instance** — no SimPy env, no `FacilityBuilder`. Match `test_collection_center_storage.py`'s style exactly (fake classes with docstrings naming what they mirror).
- Module docstring names the failure mode the file pins (see exemplar's first paragraph).
- Verbose names, no emojis, no magic numbers.
- Non-vacuity proof: for each new test, temporarily mutate the production code (e.g. make `_collect_from_cross_region` add to `collected_waste`), confirm the test goes red, then `git checkout -- core/` to restore. Mention in the commit body that each test was red-checked.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| New tests only | `/mnt/c/Python313/python.exe -m pytest tests/core/test_generator_storage.py tests/core/test_treatment_cross_region.py -q` | all pass |
| Full fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass (249 + new at planning time) |
| Restore after red-check | `git checkout -- core/` | working tree clean of core/ edits |

Run from the repo root; always `/mnt/c/Python313/python.exe`.

## Scope

**In scope**:

- `tests/core/test_generator_storage.py` (create)
- `tests/core/test_treatment_cross_region.py` (create)

**Out of scope** (do NOT touch):

- ANY file under `core/`, `models/`, `utils/` — production edits are permitted only transiently for the red-check and must be fully reverted (`git status` must show no `core/` modifications at the end).
- Existing test files.
- Do not "fix" finding-shaped behavior you notice while writing these tests (e.g. the all-or-nothing storage drop — that is Plan 004's deliberate change; here you pin the CURRENT behavior).

## Git workflow

- Commit message style: imperative, <72 chars, no colon after verb. Suggested: `Pin generator storage cap and cross-region double-count guard` (or two commits, one per file).
- No `Co-Authored-By`. Do NOT push.

## Steps

### Step 1: Read the exemplars

Read `tests/core/test_collection_center_storage.py`, `tests/core/test_treatment_flow_logging.py`, and `tests/core/conftest.py` in full. Note how `FakeCollector`/`FakeCenter` mirror only the fields the method under test touches, and whether conftest already provides a state/monitor stub you can reuse.

**Verify**: you can name which fixture (if any) conftest provides for `SimulationState` stubbing.

### Step 2: Generator tests — `tests/core/test_generator_storage.py`

Build a minimal `WasteGenerator` stand-in the same way the exemplar builds `FakeCollector` — either instantiate the real `WasteGenerator` with stub arguments if its `__init__` allows, or call the methods unbound on a `SimpleNamespace` carrying exactly the attributes the excerpts touch (`waste_storage_capacity`, `current_storage`, `waste_streams`, `waste_generation_rates`, `total_generated`, `total_potential_generated`, `efficiency`, `status`, `uncertainty_set`, `history_index`, `state`, `region`, plus whatever `_calculate_daily_factors` and `_update_waste_stream` need — read both methods first). Tests:

1. `test_potential_generation_accrues_even_when_storage_is_full` — capacity exhausted; after `_generate_waste_for_period`, `total_potential_generated[type]` grew by the full potential while `total_generated[type]` and `current_storage` are unchanged.
2. `test_type_exceeding_available_storage_generates_nothing` — two waste types where type 1 fits and type 2's potential exceeds the remainder: type 1 stored in full, type 2 stored ZERO (pins the current all-or-nothing semantics; Plan 004 will deliberately flip this test).
3. `test_update_waste_stream_reports_added_volume_to_state` — `_update_waste_stream` increments stream volume / `current_storage` / `total_generated` consistently and calls `state.track_add_waste` with the same volume (use a recording stub for `state`).
4. `test_handle_overflow_caps_storage_and_reports_every_removal` — streams over capacity; after `_handle_overflow`, `current_storage <= waste_storage_capacity` and the sum of volumes passed to `state.track_remove_waste` equals the total reduction (mass conservation, mirroring the exemplar's invariant). Stub `handle_storage_event` interaction by letting the real `utils/capacity_utils.py` run with a state/monitor stub IF the exemplar shows that works; otherwise monkeypatch `handle_storage_event` within `core.generator`'s namespace and assert the scaling step alone.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/core/test_generator_storage.py -q` → all pass.

### Step 3: Treatment cross-region tests — `tests/core/test_treatment_cross_region.py`

Call `TreatmentOperator._collect_from_cross_region` unbound on a `SimpleNamespace` with: `region_type` (a real `RegionType`), `state` (stub with `.collectors` list), and a recording `_request_via_transport` (bind a stub function; calling the method unbound means `self._request_via_transport` resolves to your stub attribute). Stub collectors are `SimpleNamespace(region_type=<other RegionType>, availability=True)`. Tests:

1. `test_cross_region_never_mutates_collected_waste` — transport stub returns `{some_type: 10.0}`; `collected_waste` dict passed in stays empty (THE double-count guard, ADR 0009).
2. `test_cross_region_return_is_unsatisfied_remainder` — request 100, transport supplies 60 total → returns 40; supplies everything → returns 0 (use `pytest.approx`).
3. `test_cross_region_consults_at_most_three_nearest_remote_collectors` — five remote collectors at increasing distances, transport stub records which collectors it saw → only the 3 nearest; a same-region collector in `state.collectors` is never consulted.
4. `test_zero_or_negative_request_short_circuits` — `amount_to_collect=0` returns `0.0` and the transport stub was never called.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/core/test_treatment_cross_region.py -q` → all pass.

### Step 4: Red-check every test, then restore

For each test, make one targeted mutation in `core/` that the test claims to guard (e.g.: add `collected_waste[waste_type] = amount` inside `_collect_from_cross_region`'s loop; change `[:3]` to `[:4]`; make `_generate_waste_for_period` skip the `total_potential_generated` accrual). Run the test, confirm RED, restore with `git checkout -- core/`.

**Verify**: after all red-checks, `git status` shows no modifications under `core/`; full suite green: `/mnt/c/Python313/python.exe -m pytest tests/ -q`.

## Test plan

This plan IS the test plan — 8 new tests across 2 files, exemplar `tests/core/test_collection_center_storage.py`, each red-checked per Step 4.

## Done criteria

- [ ] Both new files exist with the 8 named tests (names may be adapted, coverage may not shrink)
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0 with at least 257 passed
- [ ] `git status` shows changes only under `tests/core/` and `plans/`
- [ ] Commit body states the red-check was performed
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- The excerpts in "Current state" don't match the live code (drift — especially if Plan 004 landed first, which would flip test 2's expected behavior; in that case pin the NEW capped behavior instead and say so).
- A method under test cannot be driven without a real SimPy environment after a genuine attempt (report which dependency blocks it rather than building heavy scaffolding).
- A red-check mutation does NOT make its test fail (the test is vacuous — rework it, and if you cannot, report it).

## Maintenance notes

- Test 2 (`test_type_exceeding_available_storage_generates_nothing`) pins behavior Plan 004 deliberately changes; Plan 004's executor must update this one test (red→green flip is the point — it documents the semantic change in the diff).
- If `_collect_from_cross_region`'s `[:3]` nearest-collector constant ever moves to `config/constants.py`, update test 3 to read the constant.
- Reviewer scrutiny: confirm the fakes mirror real attribute names (a fake drifting from the real entity tests nothing).
