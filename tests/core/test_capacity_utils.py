"""Storage-overflow handling conserves and attributes mass (issue 11, Finding A).

``handle_storage_event`` decides expand-vs-landfill and, on the landfill branch,
must attribute the landfilled raw-waste volume to the dumping entity via
``state.track_waste_landfilled`` -- the per-entity discard term the
collection-center mass-balance invariant reads. The expand branch grows capacity
and must not record a landfill (no mass leaves the system there).
"""

from types import SimpleNamespace

from models.enums import RegionType
from models.state import SimulationState
from utils.capacity_utils import handle_storage_event


def make_entity(state, capacity=1000.0, name="collector-1"):
    """A storage-bearing entity stand-in handle_storage_event can act on.

    A no-op monitor stub stands in for WasteMonitor: the landfill branch calls
    track_environmental_impact unconditionally, so the attribute must exist.
    """
    monitor = SimpleNamespace(
        track_event=lambda **kwargs: None,
        track_environmental_impact=lambda **kwargs: None,
    )
    return SimpleNamespace(
        name=name,
        facility_type="collector",
        env=SimpleNamespace(now=3.0),
        waste_monitor=monitor,
        state=state,
        waste_storage_capacity=capacity,
        expansion_count=0,
        landfill_count=0,
    )


def test_landfill_branch_attributes_volume_to_entity():
    state = SimulationState()
    entity = make_entity(state)

    _cost, action = handle_storage_event(
        entity, 100.0, RegionType.PODRAVSKA, force_landfill=True
    )

    assert action == "landfill"
    assert state.waste_landfilled == {"collector-1": 100.0}


def test_expand_branch_records_no_landfill():
    state = SimulationState()
    entity = make_entity(state)

    # Overflow > ~1812 m³ makes expansion cheaper than landfill, so the expand
    # branch is taken; no raw waste is landfilled there.
    _cost, action = handle_storage_event(entity, 2000.0, RegionType.PODRAVSKA)

    assert action == "expand_storage"
    assert state.waste_landfilled == {}
