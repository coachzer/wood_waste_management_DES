"""Generator storage cap: all-or-nothing drop and mass-conservation invariants.

Pins three failure modes in ``WasteGenerator``:

1. ``total_potential_generated`` must accrue the full offered volume for every
   waste type even when nothing enters storage (ADR 0005 source-variance floor).
   A future change that moves the accrual inside the capacity guard would silently
   couple the bullwhip floor to policy and break reproducibility across combos.

2. When a type's potential exceeds available headroom the current code drops the
   entire type -- zero is stored, not a partial fill. Plan 004 deliberately flips
   this test to the capped-at-headroom semantics; until then, the all-or-nothing
   drop is the documented behavior and must be pinned.

3. ``_handle_overflow`` conserves mass: every m³ it removes from streams is
   reported via ``state.track_remove_waste``; nothing silently vanishes.
"""

from types import SimpleNamespace

import pytest

from core.generator import WasteGenerator
from models.data_classes import WasteStream
from models.enums import EntityStatus, WasteType


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class RecordingState:
    """Mirrors the generator-side calls to SimulationState.

    Records every ``track_add_waste`` and ``track_remove_waste`` invocation so
    tests can assert on the volumes without spinning up a real
    ``SimulationState``.
    """

    def __init__(self):
        self.added = []
        self.removed = []

    def track_add_waste(self, region, waste_type, amount):
        self.added.append((waste_type, amount))

    def track_remove_waste(self, region, waste_type, amount):
        self.removed.append((waste_type, amount))


def make_generator_stub(
    waste_generation_rates,
    waste_storage_capacity,
    current_storage=0.0,
    status=EntityStatus.OPERATIONAL,
    uncertainty_set=None,
    region=None,
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

    # generation_history needed by _update_waste_stream
    history_size = 10
    import numpy as np
    generation_history = {
        waste_type: {
            "times": np.zeros(history_size),
            "volumes": np.zeros(history_size),
            "totals": np.zeros(history_size),
            "storage": np.zeros(history_size),
        }
        for waste_type in waste_generation_rates
    }

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
        generation_history=generation_history,
        efficiency=1.0,
        status=status,
        uncertainty_set=uncertainty_set,
        history_index=0,
        state=state,
        region=region,
    )
    import types
    stub._calculate_daily_factors = types.MethodType(_calculate_daily_factors_stub, stub)
    # Bind the real _update_waste_stream so _generate_waste_for_period can call it.
    stub._update_waste_stream = types.MethodType(WasteGenerator._update_waste_stream, stub)
    return stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_potential_generation_accrues_even_when_storage_is_full():
    """ADR 0005 floor: total_potential_generated grows by the full offered volume
    even when storage is completely full and nothing enters committed storage.

    Guards the policy-invariant source-variance floor: if the accrual were
    skipped on a full-storage tick the floor would shrink under high-inventory
    policies, coupling the bullwhip denominator to policy and invalidating the
    comparison.
    """
    base_rate = 10.0
    capacity = 100.0
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: base_rate},
        waste_storage_capacity=capacity,
        current_storage=capacity,  # full -- no room
    )

    seasonal = 1.0
    current_time = 0.0
    WasteGenerator._generate_waste_for_period(stub, seasonal, current_time)

    expected_potential = base_rate * seasonal * 1.0 * 1.0  # efficiency=1, factor=1
    assert stub.total_potential_generated[CONSTRUCTION] == pytest.approx(expected_potential)
    # Nothing committed
    assert stub.total_generated[CONSTRUCTION] == 0.0
    assert stub.current_storage == capacity
    assert stub.state.added == []


def test_type_exceeding_available_storage_is_capped_at_headroom():
    """Capped partial-fill: when a type's potential exceeds remaining headroom
    it generates exactly the available headroom, not zero and not the full
    potential.

    Plan 004 changed the all-or-nothing drop to min(potential, available).
    This test documents that semantic and replaces the prior
    test_type_exceeding_available_storage_generates_nothing.

    Scenario: capacity=100, storage=90 (10 left).
    Type 1 potential=8 (fits in full -- uses 8 of 10).
    Type 2 potential=15 (exceeds the 2 remaining) -> capped at 2.
    After both: current_storage == capacity.

    Also checks the zero-headroom edge: once the first type exhausts all
    headroom, a subsequent type with positive potential generates exactly 0
    and _update_waste_stream is NOT called for it (no zero-volume churn).
    """
    capacity = 100.0
    initial_storage = 90.0
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: 8.0, PACKAGING: 15.0},
        waste_storage_capacity=capacity,
        current_storage=initial_storage,
    )

    WasteGenerator._generate_waste_for_period(stub, seasonal_factor=1.0, current_time=0.0)

    # Type 1 fits in full (8 <= 10 headroom)
    assert stub.waste_streams[CONSTRUCTION].volume == pytest.approx(8.0)
    assert stub.total_generated[CONSTRUCTION] == pytest.approx(8.0)

    # Type 2 is capped at the 2 remaining m3 (not zero, not 15)
    assert stub.waste_streams[PACKAGING].volume == pytest.approx(2.0)
    assert stub.total_generated[PACKAGING] == pytest.approx(2.0)

    # Storage must equal capacity -- all headroom consumed
    assert stub.current_storage == pytest.approx(capacity)

    # Potential recorded for both types at full offered volume (ADR 0005 floor)
    assert stub.total_potential_generated[CONSTRUCTION] == pytest.approx(8.0)
    assert stub.total_potential_generated[PACKAGING] == pytest.approx(15.0)

    # Zero-headroom edge: once storage is full, a third type generates exactly 0
    import types
    calls = []

    def recording_update(self, waste_type, volume, current_time, history_index):
        calls.append((waste_type, volume))

    from models.enums import WasteType as WT
    BARK = WT.BARK_CORK_WASTE_03_01_01
    stub2 = make_generator_stub(
        waste_generation_rates={BARK: 5.0},
        waste_storage_capacity=capacity,
        current_storage=capacity,  # no room at all
    )
    stub2._update_waste_stream = types.MethodType(recording_update, stub2)

    WasteGenerator._generate_waste_for_period(stub2, seasonal_factor=1.0, current_time=0.0)

    assert stub2.waste_streams[BARK].volume == pytest.approx(0.0)
    assert calls == [], "_update_waste_stream must not be called when headroom is zero"


def test_update_waste_stream_reports_added_volume_to_state():
    """_update_waste_stream increments stream volume, current_storage, and
    total_generated atomically, and calls state.track_add_waste with the
    identical volume.

    Guards against a split-brain where the internal counters and the external
    tracker diverge.
    """
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: 1.0},
        waste_storage_capacity=500.0,
        current_storage=0.0,
        region="podravska",
    )

    volume_to_add = 42.0
    WasteGenerator._update_waste_stream(
        stub, CONSTRUCTION, volume_to_add, current_time=5.0, history_index=0
    )

    assert stub.waste_streams[CONSTRUCTION].volume == pytest.approx(volume_to_add)
    assert stub.current_storage == pytest.approx(volume_to_add)
    assert stub.total_generated[CONSTRUCTION] == pytest.approx(volume_to_add)

    # state.track_add_waste must have been called with the same volume
    assert len(stub.state.added) == 1
    recorded_type, recorded_volume = stub.state.added[0]
    assert recorded_type == CONSTRUCTION
    assert recorded_volume == pytest.approx(volume_to_add)


def test_handle_overflow_caps_storage_and_reports_every_removal():
    """Mass conservation after overflow: _handle_overflow scales streams down to
    capacity and every m³ it removes is reported via state.track_remove_waste.

    The sum of track_remove_waste volumes plus the final current_storage must
    equal the pre-overflow total -- nothing silently vanishes.

    Uses a monkeypatched handle_storage_event stub so the test does not depend
    on landfill-vs-expand cost arithmetic; the invariant being tested is the
    scaling step and the track_remove_waste calls that follow it.
    """
    capacity = 100.0
    # Prime streams above capacity to force the scaling branch
    stub = make_generator_stub(
        waste_generation_rates={CONSTRUCTION: 1.0, PACKAGING: 1.0},
        waste_storage_capacity=capacity,
        current_storage=130.0,
        region="podravska",
    )
    stub.waste_streams[CONSTRUCTION].volume = 80.0
    stub.waste_streams[PACKAGING].volume = 50.0

    pre_overflow_total = 130.0  # 80 + 50

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

    # Every removed m³ was reported to state
    total_removed_reported = sum(vol for _, vol in stub.state.removed)
    assert total_removed_reported == pytest.approx(pre_overflow_total - capacity)

    # Mass conservation identity
    assert total_stored + total_removed_reported == pytest.approx(pre_overflow_total)
