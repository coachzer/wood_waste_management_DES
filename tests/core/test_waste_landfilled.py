"""Per-entity raw-waste landfill counter on SimulationState (issue 11, Finding A).

The collection-center waste invariant (mass_balance) needs landfilled raw waste
attributed to the entity that dumped it -- the existing WasteMonitor.track_event
only keeps a single global, entity-less bucket. This counter is a per-name
accumulator the invariant reads.
"""

from models.state import SimulationState


def test_landfill_accumulates_per_entity():
    state = SimulationState()

    state.track_waste_landfilled("collector-1", 30.0)
    state.track_waste_landfilled("collector-1", 12.5)
    state.track_waste_landfilled("collector-2", 4.0)

    assert state.waste_landfilled == {"collector-1": 42.5, "collector-2": 4.0}


def test_landfill_counter_is_empty_by_construction():
    assert SimulationState().waste_landfilled == {}


def test_reset_clears_landfill_counter():
    state = SimulationState()
    state.track_waste_landfilled("collector-1", 9.0)

    state.reset()

    assert state.waste_landfilled == {}
