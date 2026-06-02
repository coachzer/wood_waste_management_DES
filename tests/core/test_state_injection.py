"""SimulationState is injected, not a singleton (arch-04).

Two runs must be able to hold independent state in one process without the
old ``_instance = None`` reset ritual. These tests pin that contract so the
singleton cannot creep back.
"""

from models.state import SimulationState


def test_two_instances_are_independent():
    """Mutating one instance must not leak into another."""
    first = SimulationState()
    second = SimulationState()

    assert first is not second

    first.record_consumption_event(
        operator_name="op_a", product="mdf", attempted=10.0, consumed=4.0,
        reason="stockout", timestamp=7.0,
    )
    first.production_discarded["mdf"] = 3.0

    # The second instance is untouched.
    assert second.consumption_events == []
    assert second.production_discarded["mdf"] == 0.0
    assert len(first.consumption_events) == 1


def test_singleton_machinery_is_gone():
    """The global-singleton accessors must stay deleted."""
    assert not hasattr(SimulationState, "_instance")
    assert not hasattr(SimulationState, "get_instance")
