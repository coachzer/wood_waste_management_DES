"""Storage-overflow handling conserves and attributes mass (issue 11, Finding A).

``handle_storage_event`` decides expand-vs-landfill and, on the landfill branch,
must attribute the landfilled raw-waste volume to the dumping entity via
``state.track_waste_landfilled`` -- the per-entity discard term the
collection-center mass-balance invariant reads. The expand branch grows capacity
and must not record a landfill (no mass leaves the system there).
"""

from types import SimpleNamespace

import pytest

from models.enums import WasteType
from models.state import SimulationState
from utils.capacity_utils import check_storage_capacity, handle_storage_event

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
PAPER = WasteType.PAPER_PACKAGING_15_01_01


def make_entity(state, capacity=1000.0, name="collector-1"):
    """A storage-bearing entity stand-in handle_storage_event can act on.

    A no-op monitor stub stands in for WasteMonitor so the recording calls have
    somewhere to go; the monitor-less case is covered separately below.
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

    _cost, action = handle_storage_event(entity, {SAWDUST: 100.0}, force_landfill=True)

    assert action == "landfill"
    assert state.waste_landfilled == {"collector-1": 100.0}


def test_expand_branch_records_no_landfill():
    state = SimulationState()
    entity = make_entity(state)

    # Landfill cost is now composition-dependent (ADR 0013). Pure PAPER has density
    # 600 kg/m³ = the retired flat 0.6 t/m³, so it preserves the original ~1812 m³
    # break-even: at 2000 m³ landfilling costs more than one expansion, so the
    # expand branch is taken and no raw waste is landfilled there.
    _cost, action = handle_storage_event(entity, {PAPER: 2000.0})

    assert action == "expand_storage"
    assert state.waste_landfilled == {}


def test_landfill_cost_is_per_type_density_weighted():
    """Landfill cost weights each waste type by its OWN density, not a flat 0.6
    (ADR 0013). 100 m³ of PAPER (600 kg/m³) costs 3x 100 m³ of SAWDUST (200 kg/m³).

    Non-vacuity: the retired flat-density formula would charge the whole 200 m³ at
    0.6 t/m³ = 200*0.6*46 = 5520 USD; the per-type formula charges
    100*0.6*46 + 100*0.2*46 = 3680 USD, so the assertion fails under the old code.
    Expected is computed from WASTE_DENSITIES so it is not a hand-pinned literal.
    """
    from config.constants import KILOGRAMS_PER_TONNE, LANDFILL_COST_PER_TONNE_USD, WASTE_DENSITIES

    state = SimulationState()
    entity = make_entity(state)

    cost, action = handle_storage_event(
        entity, {PAPER: 100.0, SAWDUST: 100.0}, force_landfill=True
    )

    expected = sum(
        volume * (WASTE_DENSITIES[waste_type] / KILOGRAMS_PER_TONNE)
        * LANDFILL_COST_PER_TONNE_USD
        for waste_type, volume in {PAPER: 100.0, SAWDUST: 100.0}.items()
    )
    assert action == "landfill"
    assert cost == pytest.approx(expected)
    assert cost == pytest.approx(3680.0)  # 100*0.6*46 + 100*0.2*46


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


# --- split_overflow_by_type: proportional apportionment of a scalar overflow --
# A scalar overflow volume is split back across the composition that produced it
# in the same type-ratio check_storage_capacity scales by, so the per-type
# landfill-cost path (ADR 0013) can weight each type by its own density.


def test_split_overflow_by_type_is_proportional():
    """60 m³ overflow against an equal 50/50 SAWDUST/PAPER mix splits 30/30 --
    proportional to composition, not first-come. Non-vacuity: a 90/10 mix would
    split 54/6, so the assertion is sensitive to the ratio it claims to test."""
    from utils.capacity_utils import split_overflow_by_type

    result = split_overflow_by_type({SAWDUST: 50.0, PAPER: 50.0}, 60.0)

    assert result[SAWDUST] == pytest.approx(30.0)
    assert result[PAPER] == pytest.approx(30.0)


# --- Guard-asymmetry regression (fixed by utils-cleanup issue 05) ------------


def make_monitorless_entity(name="collector-nomon"):
    """A storage-bearing entity with NO waste_monitor attribute at all.

    Real entities always inject a monitor, but handle_storage_event's landfill
    branch used to call track_environmental_impact outside the
    hasattr(waste_monitor) guard that wraps track_event, so a monitor-less entity
    reaching that branch raised AttributeError. state=None keeps
    track_waste_landfilled out of the way so the test isolates the monitor guard.
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


def test_landfill_branch_survives_missing_monitor():
    """A monitor-less entity forced down the landfill branch must NOT crash. The
    fix brings track_environmental_impact under the same waste_monitor guard as
    track_event, so the landfill resolves (action == "landfill") without raising.
    Pre-fix this raised AttributeError on the unguarded call."""
    entity = make_monitorless_entity()

    _cost, action = handle_storage_event(entity, {SAWDUST: 100.0}, force_landfill=True)

    assert action == "landfill"
