"""Generator storage cap: headroom capping and mass-conservation invariants.

Pins three failure modes in ``WasteGenerator``:

1. ``total_potential_generated`` must accrue the full offered volume for every
   waste type even when nothing enters storage (ADR 0005 source-variance floor).
   A future change that moves the accrual inside the capacity guard would silently
   couple the bullwhip floor to policy and break reproducibility across combos.

2. When a type's potential exceeds available headroom it stores exactly the
   headroom (plan 004), and a type that finds none stores nothing.

3. ``_handle_overflow`` conserves mass: the volume it removes from streams is
   exactly the excess over capacity; nothing silently vanishes.
"""

from types import SimpleNamespace

import pytest
import simpy

from config.constants import OPERATING_TICK_DAYS
from core.generator import WasteGenerator
from models.data_classes import WasteStream
from models.enums import EntityStatus, WasteType
from tests.core.factories import make_waste_generator


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03
BARK = WasteType.BARK_CORK_WASTE_03_01_01


def run_one_generation_tick(waste_monitor, generation_rates, **overrides):
    """A real generator after its t=0 tick (seasonal factor 1.0, unit daily factor)."""
    env = simpy.Environment()
    generator = make_waste_generator(env, waste_monitor, generation_rates, **overrides)
    env.run(until=OPERATING_TICK_DAYS / 2)
    return generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class RecordingState:
    """Stands in for SimulationState.

    The generator storage path no longer calls back into state, so this is an
    inert placeholder that satisfies the ``self.state`` attribute without
    spinning up a real ``SimulationState``.
    """


def make_generator_stub(
    waste_generation_rates,
    waste_storage_capacity,
    current_storage=0.0,
    status=EntityStatus.OPERATIONAL,
    outlet_waste_types=(),
):
    """Build a minimal SimpleNamespace that satisfies ``_generate_waste_for_period``.

    Mirrors only the attributes those methods actually read, using the same
    field names as the real ``WasteGenerator``.
    """
    state = RecordingState()

    waste_streams = {
        waste_type: WasteStream(waste_type=waste_type, volume=0.0)
        for waste_type in waste_generation_rates
    }

    total_generated = {waste_type: 0.0 for waste_type in waste_generation_rates}
    total_potential_generated = {waste_type: 0.0 for waste_type in waste_generation_rates}
    total_uncollected = {waste_type: 0.0 for waste_type in waste_generation_rates}

    def _calculate_daily_factors_stub(self):
        """No uncertainty: return unit factor for every waste type."""
        return [1.0] * len(self.waste_generation_rates)

    stub = SimpleNamespace(
        waste_generation_rates=waste_generation_rates,
        waste_storage_capacity=waste_storage_capacity,
        current_storage=current_storage,
        waste_streams=waste_streams,
        total_generated=total_generated,
        total_potential_generated=total_potential_generated,
        total_uncollected=total_uncollected,
        outlet_waste_types=frozenset(outlet_waste_types),
        total_outlet={waste_type: 0.0 for waste_type in waste_generation_rates},
        efficiency=1.0,
        status=status,
        state=state,
    )
    import types
    stub._calculate_daily_factors = types.MethodType(_calculate_daily_factors_stub, stub)
    # Bind the real _update_waste_stream so _generate_waste_for_period can call it.
    stub._update_waste_stream = types.MethodType(WasteGenerator._update_waste_stream, stub)
    return stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_potential_generation_accrues_even_when_storage_is_full(ledger_waste_monitor):
    """ADR 0005 floor: total_potential_generated grows by the full offered volume
    even when storage is completely full and nothing enters committed storage.

    Guards the policy-invariant source-variance floor: if the accrual were
    skipped on a full-storage tick the floor would shrink under high-inventory
    policies, coupling the bullwhip denominator to policy and invalidating the
    comparison.
    """
    generator = run_one_generation_tick(
        ledger_waste_monitor, {CONSTRUCTION: 10.0}, waste_storage_capacity=100.0,
        initial_stock={CONSTRUCTION: 100.0},
    )

    assert generator.total_potential_generated[CONSTRUCTION] == pytest.approx(100.0 + 10.0)
    assert generator.total_generated[CONSTRUCTION] == 100.0
    assert generator.total_uncollected[CONSTRUCTION] == pytest.approx(10.0)
    assert generator.current_storage == 100.0


def test_type_exceeding_available_storage_is_capped_at_headroom(ledger_waste_monitor):
    """Capped partial-fill: when a type's potential exceeds remaining headroom
    it generates exactly the available headroom, not zero and not the full
    potential (plan 004: min(potential, available)).

    Scenario: capacity=100, storage=90 (10 left).
    Type 1 potential=8 (fits in full -- uses 8 of 10).
    Type 2 potential=15 (exceeds the 2 remaining) -> capped at 2.
    Type 3 potential=5 finds no headroom left and stores nothing.
    """
    generator = run_one_generation_tick(
        ledger_waste_monitor, {CONSTRUCTION: 8.0, PACKAGING: 15.0, BARK: 5.0},
        waste_storage_capacity=100.0, initial_stock={BARK: 90.0},
    )

    assert generator.waste_streams[CONSTRUCTION].volume == pytest.approx(8.0)
    assert generator.waste_streams[PACKAGING].volume == pytest.approx(2.0)
    assert generator.waste_streams[BARK].volume == pytest.approx(90.0)
    assert generator.current_storage == pytest.approx(100.0)

    # Potential recorded for every type at full offered volume (ADR 0005 floor)
    assert generator.total_potential_generated[PACKAGING] == pytest.approx(15.0)
    assert generator.total_uncollected == pytest.approx({CONSTRUCTION: 0.0, PACKAGING: 13.0, BARK: 5.0})


def test_update_waste_stream_increments_all_counters_atomically():
    """_update_waste_stream increments stream volume, current_storage, and
    total_generated atomically with the identical volume.

    Guards against a split-brain where the three internal counters diverge.
    """
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: 1.0},
        waste_storage_capacity=500.0,
        current_storage=0.0,
    )

    volume_to_add = 42.0
    WasteGenerator._update_waste_stream(
        stub, CONSTRUCTION, volume_to_add
    )

    assert stub.waste_streams[CONSTRUCTION].volume == pytest.approx(volume_to_add)
    assert stub.current_storage == pytest.approx(volume_to_add)
    assert stub.total_generated[CONSTRUCTION] == pytest.approx(volume_to_add)


def test_handle_overflow_caps_storage_and_scales_streams_proportionally():
    """Mass conservation after overflow: _handle_overflow scales streams down to
    capacity, and the volume removed is exactly the excess over capacity.

    The per-stream reductions plus the final stored total must equal the
    pre-overflow total, and every stream must shrink by the same factor --
    nothing silently vanishes and no type is singled out.

    Uses a monkeypatched handle_storage_event stub so the test does not depend
    on landfill-vs-expand cost arithmetic; the invariant being tested is the
    scaling step alone.
    """
    capacity = 100.0
    # Prime streams above capacity to force the scaling branch
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: 1.0, PACKAGING: 1.0},
        waste_storage_capacity=capacity,
        current_storage=130.0,
    )
    pre_overflow_volumes = {CONSTRUCTION: 80.0, PACKAGING: 50.0}
    for waste_type, volume in pre_overflow_volumes.items():
        stub.waste_streams[waste_type].volume = volume

    pre_overflow_total = sum(pre_overflow_volumes.values())  # 130

    # Stub handle_storage_event so it performs no side effects on capacity or
    # streams; we are testing the scaling step that follows it.
    import unittest.mock as mock
    with mock.patch("core.generator.handle_storage_event"):
        WasteGenerator._handle_overflow(stub, force_landfill=False)

    # Storage must be capped at capacity
    assert stub.current_storage == pytest.approx(capacity)

    # Sum of volumes across streams must equal capacity
    total_stored = sum(s.volume for s in stub.waste_streams.values())
    assert total_stored == pytest.approx(capacity)

    # Every stream shrank by the same factor (proportional, not type-biased)
    expected_scaling_factor = capacity / pre_overflow_total
    for waste_type, pre_volume in pre_overflow_volumes.items():
        assert stub.waste_streams[waste_type].volume == pytest.approx(
            pre_volume * expected_scaling_factor
        )

    # Mass conservation identity: removed volume is exactly the excess
    total_removed = sum(
        pre_volume - stub.waste_streams[waste_type].volume
        for waste_type, pre_volume in pre_overflow_volumes.items()
    )
    assert total_removed == pytest.approx(pre_overflow_total - capacity)
    assert total_stored + total_removed == pytest.approx(pre_overflow_total)


def test_outlet_type_leaves_without_taking_storage(ledger_waste_monitor):
    """ADR 0036: a type no processor accepts goes to the outlet and leaves storage to the rest.

    Mutation check (red): drop the outlet branch, so the outlet type fills storage first.
    """
    generator = run_one_generation_tick(
        ledger_waste_monitor, {PACKAGING: 8.0, CONSTRUCTION: 10.0},
        waste_storage_capacity=10.0, accepted_waste_types=[CONSTRUCTION],
    )

    assert generator.total_outlet[PACKAGING] == pytest.approx(8.0)
    assert generator.total_generated[PACKAGING] == 0.0
    assert generator.total_uncollected[PACKAGING] == 0.0
    assert generator.total_potential_generated[PACKAGING] == pytest.approx(8.0)
    assert generator.total_generated[CONSTRUCTION] == pytest.approx(10.0)
    assert generator.total_uncollected[CONSTRUCTION] == 0.0
    assert generator.current_storage == pytest.approx(10.0)
