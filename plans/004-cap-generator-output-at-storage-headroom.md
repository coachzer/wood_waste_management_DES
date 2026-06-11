# Plan 004: Cap per-type waste generation at remaining storage headroom instead of dropping it entirely

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 105eacc..HEAD -- core/generator.py tests/core/test_generator_storage.py`
> Plan 003 landing first is EXPECTED drift (it creates the test file). Any
> other change to `core/generator.py` since `105eacc`: compare the "Current
> state" excerpt before proceeding; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: S (code) — but the change shifts simulation results; see Maintenance notes
- **Risk**: MED — oracle-affecting: KPI values across all combos will move; determinism tests still pass (they compare across invocations, not against stored values)
- **Depends on**: plans/003-characterization-tests-generator-and-cross-region.md (the safety net; one of its tests is deliberately flipped here)
- **Category**: bug
- **Planned at**: commit `105eacc`, 2026-06-11

## Why this matters

In `WasteGenerator._generate_waste_for_period`, a waste type whose potential volume exceeds the remaining storage headroom generates **nothing** that tick — not a capped partial amount. The project's own domain documentation (CONTEXT.md, Throughput Bullwhip entry) describes committed generation as "capped by storage headroom", i.e. partial-fill semantics; the code implements all-or-nothing drop instead. Consequences: `total_generated` is understated for multi-type generators near capacity, which **overstates** `collection_rate_pct` (= collected / generated), and the suppression depends on dict iteration order of `waste_generation_rates` (earlier types get the headroom, later types get zeroed). The ADR 0005 potential-generation floor is unaffected (recorded before the cap), but the committed-generation series that backpressure couples to policy is distorted in a non-physical way.

## Current state

`core/generator.py:247-269` (`_generate_waste_for_period`):

```python
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

`_update_waste_stream` is at `core/generator.py:191`; it adds the given volume to the stream, `current_storage`, `total_generated`, and reports it via `state.track_add_waste`.

After Plan 003, `tests/core/test_generator_storage.py` exists and contains `test_type_exceeding_available_storage_generates_nothing`, which pins the CURRENT all-or-nothing behavior — this plan deliberately flips that test.

Conventions: verbose names; no magic numbers; surgical change only (touch nothing else in the loop — in particular the `total_potential_generated` accrual must stay exactly where it is, before the cap, per ADR 0005).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Generator tests | `/mnt/c/Python313/python.exe -m pytest tests/core/test_generator_storage.py -q` | all pass |
| Full fast suite | `/mnt/c/Python313/python.exe -m pytest tests/ -q` | all pass |
| Determinism backstop | `/mnt/c/Python313/python.exe -m pytest tests/test_determinism.py tests/test_enum_set_ordering.py -q` | all pass |

Run from repo root; always `/mnt/c/Python313/python.exe`.

## Scope

**In scope**:

- `core/generator.py` — the `if potential_volume <= available_storage:` block only (around line 265)
- `tests/core/test_generator_storage.py` — update the one flipped test, add one new test

**Out of scope** (do NOT touch):

- `total_potential_generated` accrual (ADR 0005 floor — policy-invariant by construction; moving it breaks the bullwhip source floor).
- `_handle_overflow`, `_update_waste_stream`, any other generator method.
- `core/collector.py`, `core/treatment.py` storage paths — they have their own overflow semantics (`handle_storage_event`); this plan is generator-only.
- Regenerating `outputs/` — maintainer's call (see Maintenance notes).

## Git workflow

- Suggested message: `Cap per-type generation at storage headroom` with a body explaining the all-or-nothing drop, the CONTEXT.md "capped by storage headroom" language, and that downstream KPI values shift.
- No `Co-Authored-By`. Do NOT push.

## Steps

### Step 1: Flip the pinned test to the capped semantics (red first)

In `tests/core/test_generator_storage.py`, rewrite `test_type_exceeding_available_storage_generates_nothing` as `test_type_exceeding_available_storage_is_capped_at_headroom`: with headroom H left and potential P > H, the type must generate exactly H (use `pytest.approx`), `current_storage` must equal capacity afterwards, and `total_potential_generated` must still accrue the full P. Add a second case: once headroom is zero, a further type generates exactly 0 and `_update_waste_stream` is NOT called for it (no zero-volume stream churn).

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/core/test_generator_storage.py -q` → the rewritten test FAILS against current code; all others pass.

### Step 2: Implement the cap

Replace the conditional block with:

```python
            generated_volume = min(potential_volume, available_storage)
            if generated_volume > 0:
                self._update_waste_stream(
                    waste_type, generated_volume, current_time, self.history_index
                )
                available_storage -= generated_volume
```

Keep the surrounding comment about the ADR 0005 floor untouched. Do not add a comment explaining the change — the commit body carries the why.

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/core/test_generator_storage.py -q` → all pass.

### Step 3: Full suite + determinism

**Verify**: `/mnt/c/Python313/python.exe -m pytest tests/ -q` → all pass. If a mass-balance or monitoring test fails, read its docstring before reacting: a test that pinned a *consequence* of the old all-or-nothing behavior may legitimately need its expected values updated — but a test asserting conservation (mass in = mass stored + mass removed) must NEVER be weakened to pass. If a conservation test fails, STOP.

## Test plan

- Rewritten: `test_type_exceeding_available_storage_is_capped_at_headroom` (the red→green flip documents the semantic change).
- New: zero-headroom case generates 0 without calling `_update_waste_stream`.
- Pattern: same file, Plan 003's style.

## Done criteria

- [ ] `grep -n "min(potential_volume, available_storage)" core/generator.py` → one match
- [ ] `/mnt/c/Python313/python.exe -m pytest tests/ -q` exits 0
- [ ] `git status` shows changes only to `core/generator.py`, `tests/core/test_generator_storage.py`, `plans/README.md`
- [ ] Commit body states that simulation KPI values shift and outputs need regeneration
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back if:

- Plan 003 has not landed (no `tests/core/test_generator_storage.py`) — execute 003 first or report.
- The excerpt at `core/generator.py:255-269` doesn't match the live code (beyond Plan 003's test-only changes).
- A mass-conservation test fails after the change (the cap must conserve mass trivially — stored exactly `min(P, H)`; a conservation failure means a hidden coupling, e.g. `_handle_overflow` interplay, that needs maintainer review).
- You find documentation (an ADR or `.scratch/done/` record) explicitly choosing all-or-nothing generation semantics — the CONTEXT.md "capped" reading would then be contested; report instead of choosing.

## Maintenance notes

- **Oracle shift**: every KPI downstream of `total_generated` moves (collection_rate_pct down, possibly holding cost and landfill volumes). All `outputs/` artifacts predate this change; the maintainer must re-run `python main.py --mode baseline --replications 100` before citing numbers, and should expect the committed-generation CV² (the policy-coupled series noted in CONTEXT.md) to change. Report the direction of movement honestly — the previous numbers overstated collection rate.
- Reviewer scrutiny: the ADR 0005 floor accrual must be byte-identical across combos after the change (it was computed before the cap both before and after this plan; nothing should have moved).
- Deferred: whether per-type headroom allocation should be proportional rather than first-come (dict order) when multiple types compete for the last headroom. The cap removes the all-or-nothing cliff; allocation fairness across types within one tick is a smaller, separate question — open an issue if it matters for a paper claim.
