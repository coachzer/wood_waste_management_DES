"""Storage-overflow handling conserves and attributes mass (issue 11, Finding A).

``handle_storage_event`` decides expand-vs-landfill and, on the landfill branch,
must attribute the landfilled raw-waste volume to the dumping entity via the
monitor's landfill ledger (``HistoryStore.record_landfill``) -- the per-entity
discard term the collection-center mass-balance invariant reads. The expand
branch grows capacity and must not record a landfill (no mass leaves the system
there).
"""

from types import SimpleNamespace

import pytest

from models.enums import WasteType
from models.state import SimulationState
from utils.capacity_utils import check_storage_capacity, handle_storage_event, store_with_overflow

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
PAPER = WasteType.PAPER_PACKAGING_15_01_01


def make_entity(state, monitor=None, capacity=1000.0, name="collector-1"):
    """A storage-bearing entity stand-in handle_storage_event can act on.

    ``monitor`` is the shared ``noop_waste_monitor`` stub so the recording
    calls have somewhere to go, or None for a monitor-less entity.
    """
    entity = SimpleNamespace(
        name=name,
        facility_type="collector",
        env=SimpleNamespace(now=3.0),
        state=state,
        waste_storage_capacity=capacity,
        expansion_count=0,
        landfill_count=0,
        waste_monitor=monitor,
    )
    return entity


def test_landfill_branch_attributes_volume_to_entity(ledger_waste_monitor):
    state = SimulationState()
    entity = make_entity(state, ledger_waste_monitor)

    _cost, action = handle_storage_event(entity, {SAWDUST: 100.0}, force_landfill=True)

    assert action == "landfill"
    assert ledger_waste_monitor.store.landfilled_volume_by_entity() == {"collector-1": 100.0}


def test_expand_branch_records_no_landfill(ledger_waste_monitor):
    state = SimulationState()
    entity = make_entity(state, ledger_waste_monitor)

    # Landfill cost is now composition-dependent (ADR 0013). Pure PAPER has density
    # 600 kg/m³ = the retired flat 0.6 t/m³, so it preserves the original ~1812 m³
    # break-even: at 2000 m³ landfilling costs more than one expansion, so the
    # expand branch is taken and no raw waste is landfilled there.
    _cost, action = handle_storage_event(entity, {PAPER: 2000.0})

    assert action == "expand_storage"
    assert ledger_waste_monitor.store.landfill_history == {}


def test_landfill_cost_is_per_type_density_weighted(noop_waste_monitor):
    """Landfill cost weights each waste type by its OWN density, not a flat 0.6
    (ADR 0013). 100 m³ of PAPER (600 kg/m³) costs 3x 100 m³ of SAWDUST (200 kg/m³).

    The retired flat-density formula would charge the whole 200 m³ at
    0.6 t/m³ = 200*0.6*46 = 5520 USD; the per-type formula charges
    100*0.6*46 + 100*0.2*46 = 3680 USD.
    """
    state = SimulationState()
    entity = make_entity(state, noop_waste_monitor)

    cost, action = handle_storage_event(
        entity, {PAPER: 100.0, SAWDUST: 100.0}, force_landfill=True
    )

    assert action == "landfill"
    assert cost == pytest.approx(3680.0)


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


def test_landfill_branch_survives_missing_monitor():
    """A monitor-less entity forced down the landfill branch must NOT crash. Both
    ledger writes (record_landfill, record_emission) sit under the same
    waste_monitor guard, so the landfill resolves (action == "landfill") without
    raising. Pre-fix this raised AttributeError on an unguarded call."""
    entity = make_entity(state=None, name="collector-nomon")

    _cost, action = handle_storage_event(entity, {SAWDUST: 100.0}, force_landfill=True)

    assert action == "landfill"


# --- store_with_overflow: the one intake path for all three echelons (#2) -----


def test_store_with_overflow_expands_then_landfills_the_remainder(ledger_waste_monitor):
    """200 m³ stored, 3000 m³ of PAPER offered to a 1000 m³ store: the 2200 m³
    overflow is dearer to landfill than one 500 m³ expansion, so capacity grows
    to 1500, 1300 m³ is stored and the 1700 m³ that still doesn't fit is landfilled.
    Mutation check (red): skip the post-expansion landfill -> 1700 m³ lost from
    the ledger (the pre-13c9e93 behaviour)."""
    entity = make_entity(SimulationState(), ledger_waste_monitor)

    stored = store_with_overflow(entity, {PAPER: 200.0}, {PAPER: 3000.0})

    assert entity.waste_storage_capacity == 1500.0
    assert stored == {PAPER: pytest.approx(1300.0)}
    assert ledger_waste_monitor.store.landfilled_volume_by_entity() == {
        "collector-1": pytest.approx(1700.0)
    }


def test_store_with_overflow_never_takes_back_stock_from_an_overfull_store(ledger_waste_monitor):
    """A store already 0.7 m³ over its 1000 m³ capacity has no room: the 100 m³
    offered is landfilled and nothing is stored. Only the offer is landfilled, not
    the stock already held. Mutation check (red): drop both headroom guards in
    check_storage_capacity (the max(0, ...) clamp and the no-room early return),
    as the collector's own arithmetic had before #2 -> 100.7 m³ landfilled and a
    negative volume "stored"."""
    entity = make_entity(SimulationState(), ledger_waste_monitor)

    stored = store_with_overflow(entity, {PAPER: 1000.7}, {PAPER: 100.0})

    assert stored == {PAPER: 0.0}
    assert ledger_waste_monitor.store.landfilled_volume_by_entity() == {
        "collector-1": pytest.approx(100.0)
    }
