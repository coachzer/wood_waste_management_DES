"""Storage-overflow handling conserves and attributes mass (issue 11, Finding A).

``handle_storage_event`` decides expand-vs-landfill and, on the landfill branch,
must attribute the landfilled raw-waste volume to the dumping entity via
``state.track_waste_landfilled`` -- the per-entity discard term the
collection-center mass-balance invariant reads. The expand branch grows capacity
and must not record a landfill (no mass leaves the system there).
"""

from types import SimpleNamespace

import pytest

from models.enums import RegionType, WasteType
from models.state import SimulationState
from utils.capacity_utils import check_storage_capacity, handle_storage_event

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
PAPER = WasteType.PAPER_PACKAGING_15_01_01


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


# --- check_storage_capacity: the proportional-scaling overflow logic ---------
# Load-bearing on every collection allocation, previously untested directly.
# The three branches: everything fits, no capacity, partial capacity.


def test_check_storage_capacity_everything_fits():
    """Additions within the free capacity are returned unchanged with zero
    overflow -- nothing is scaled down."""
    accepted, overflow = check_storage_capacity(
        current_storage={SAWDUST: 10.0},
        additions={SAWDUST: 30.0, PAPER: 20.0},
        capacity=100.0,
    )

    assert accepted == {SAWDUST: 30.0, PAPER: 20.0}
    assert overflow == 0.0


def test_check_storage_capacity_no_capacity_overflows_all():
    """When storage is already full, nothing is accepted and the entire addition
    becomes overflow."""
    accepted, overflow = check_storage_capacity(
        current_storage={SAWDUST: 100.0},
        additions={SAWDUST: 10.0, PAPER: 5.0},
        capacity=100.0,
    )

    assert accepted == {SAWDUST: 0.0, PAPER: 0.0}
    assert overflow == pytest.approx(15.0)


def test_check_storage_capacity_partial_scales_proportionally():
    """With 40 of free capacity against 100 of additions, each waste type is
    scaled by 0.4 and the remaining 60 overflows -- proportional, not first-come."""
    accepted, overflow = check_storage_capacity(
        current_storage={SAWDUST: 60.0},
        additions={SAWDUST: 50.0, PAPER: 50.0},
        capacity=100.0,
    )

    assert accepted[SAWDUST] == pytest.approx(20.0)
    assert accepted[PAPER] == pytest.approx(20.0)
    assert overflow == pytest.approx(60.0)


# --- Guard-asymmetry regression (RED until utils-cleanup issue 05) -----------


def make_monitorless_entity(name="collector-nomon"):
    """A storage-bearing entity with NO waste_monitor attribute at all.

    Real entities always inject a monitor, but handle_storage_event's landfill
    branch calls track_environmental_impact outside the hasattr(waste_monitor)
    guard that wraps track_event, so a monitor-less entity reaching that branch
    raises AttributeError. state=None keeps track_waste_landfilled out of the way
    so the crash is isolated to the unguarded monitor call.
    """
    return SimpleNamespace(
        name=name,
        facility_type="collector",
        env=SimpleNamespace(now=3.0),
        state=None,
        waste_storage_capacity=1000.0,
        expansion_count=0,
        landfill_count=0,
    )


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="guard asymmetry: track_environmental_impact is unguarded; fixed by utils-cleanup issue 05",
)
def test_landfill_branch_survives_missing_monitor():
    """A monitor-less entity forced down the landfill branch must NOT crash.
    Today the unguarded track_environmental_impact call raises AttributeError;
    issue 05 brings it under the same guard as track_event and this passes."""
    entity = make_monitorless_entity()

    _cost, action = handle_storage_event(
        entity, 100.0, RegionType.PODRAVSKA, force_landfill=True
    )

    assert action == "landfill"
