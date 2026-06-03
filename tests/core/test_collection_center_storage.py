"""Collection-center intake conserves mass on overflow (issue 11, Finding A).

``_add_to_collection_center`` previously scaled stored waste down to the *old*
available space and then called ``handle_storage_event``; on the expand branch
that grew capacity but never stored the overflow, silently dropping ~10% of
collected waste on the Baseline seed. The corrected behavior conserves mass:
everything handed in is either stored (up to the possibly-expanded capacity) or
landfilled -- nothing vanishes.
"""

from types import SimpleNamespace

from core.collector import CollectorCompany
from models.enums import WasteType
from models.state import SimulationState


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03


class FakeCenter:
    """Mirrors CollectionCenter's two fields the storage path touches."""

    def __init__(self, capacity, storage):
        self.waste_storage_capacity = capacity
        self.current_storage = dict(storage)


class FakeCollector:
    """A collector stand-in for _add_to_collection_center.

    Replicates the real ``waste_storage_capacity`` property delegating to the
    collection center, so an expansion inside handle_storage_event is visible
    through both access paths exactly as on the real entity.
    """

    facility_type = "collector"

    def __init__(self, center, state, name="collector-1", region="podravska"):
        self.collection_center = center
        self.state = state
        self.name = name
        self.region = region
        self.expansion_count = 0
        self.env = SimpleNamespace(now=0.0)
        self.waste_monitor = SimpleNamespace(
            track_event=lambda **kwargs: None,
            track_environmental_impact=lambda **kwargs: None,
        )

    @property
    def waste_storage_capacity(self):
        return self.collection_center.waste_storage_capacity

    @waste_storage_capacity.setter
    def waste_storage_capacity(self, value):
        self.collection_center.waste_storage_capacity = value


def stored_total(collector):
    return sum(collector.collection_center.current_storage.values())


def landfilled_total(state, name="collector-1"):
    return state.waste_landfilled.get(name, 0.0)


def test_expand_branch_stores_overflow_and_landfills_remainder():
    """A large overflow takes the expand branch (capacity +500). The collected
    mass must end up stored (up to the new capacity) plus landfilled -- not
    dropped. Empty center, capacity 2000, 4000 handed in -> overflow 2000
    (> ~1812, so expand): 2500 stored (full new capacity), 1500 landfilled."""
    state = SimulationState()
    collector = FakeCollector(FakeCenter(2000.0, {CONSTRUCTION: 0.0}), state)

    CollectorCompany._add_to_collection_center(collector, {CONSTRUCTION: 4000.0})

    assert collector.collection_center.waste_storage_capacity == 2500.0
    assert stored_total(collector) == 2500.0
    assert landfilled_total(state) == 1500.0
    # Conservation: nothing collected is silently dropped.
    assert stored_total(collector) + landfilled_total(state) == 4000.0


def test_landfill_branch_conserves_mass():
    """A small overflow takes the landfill branch: what fits is stored, the
    excess is landfilled and attributed -- still conserving mass."""
    state = SimulationState()
    collector = FakeCollector(FakeCenter(2000.0, {CONSTRUCTION: 0.0}), state)

    CollectorCompany._add_to_collection_center(collector, {CONSTRUCTION: 2100.0})

    assert collector.collection_center.waste_storage_capacity == 2000.0  # no expansion
    assert stored_total(collector) == 2000.0
    assert landfilled_total(state) == 100.0
    assert stored_total(collector) + landfilled_total(state) == 2100.0


def test_no_overflow_stores_everything():
    """Within capacity, all waste is stored and nothing is landfilled."""
    state = SimulationState()
    collector = FakeCollector(FakeCenter(2000.0, {CONSTRUCTION: 0.0, PACKAGING: 0.0}), state)

    CollectorCompany._add_to_collection_center(
        collector, {CONSTRUCTION: 300.0, PACKAGING: 200.0}
    )

    assert stored_total(collector) == 500.0
    assert landfilled_total(state) == 0.0
