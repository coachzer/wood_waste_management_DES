"""Collection-center intake conserves mass on overflow (issue 11, Finding A).

Center intake previously scaled stored waste down to the *old*
available space and then called ``handle_storage_event``; on the expand branch
that grew capacity but never stored the overflow, silently dropping ~10% of
collected waste on the Baseline seed. The corrected behavior conserves mass:
everything handed in is either stored (up to the possibly-expanded capacity) or
landfilled -- nothing vanishes.
"""

import simpy

from tests.core.factories import make_collector, make_generator_site
from models.enums import WasteType


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03
PAPER = WasteType.PAPER_PACKAGING_15_01_01  # 600 kg/m³ = the retired flat density


def _dispatch_all_vehicles(monitor, volume_by_type):
    """Send every vehicle at once to one generator; return (collector, landfilled).

    Each dispatch claims the center headroom it sees at t=0, so the vehicles that
    unload later overflow the center. Per-tick capacity 2000, center 4000.
    """
    env = simpy.Environment()
    collector = make_collector(
        env, monitor, waste_types=list(volume_by_type),
        collection_capacity=2000.0, collection_frequency=1,
    )
    generator = make_generator_site(volume_by_type)
    for _ in collector.vehicles:
        collector.collect_from_generator(generator)
    env.run(until=0.9)
    landfilled = monitor.store.landfilled_volume_by_entity().get(collector.name, 0.0)
    return collector, landfilled


def stored_total(collector):
    return sum(collector.collection_center.current_storage.values())


def test_expand_branch_stores_overflow_and_landfills_remainder(ledger_waste_monitor):
    """Three 2000 m3 loads into a 4000 m3 center overflow by 2000 (> ~1812, so
    expand): capacity grows by 500, 4500 is stored and 1500 landfilled.

    Uses PAPER (600 kg/m³): per-type landfill cost (ADR 0013) only exceeds the
    expansion cost at this overflow for streams at/above the retired flat 0.6
    density. The mass figures are volume-based and density-independent."""
    collector, landfilled = _dispatch_all_vehicles(ledger_waste_monitor, {PAPER: 6000.0})

    assert collector.collection_center.waste_storage_capacity == 4500.0
    assert stored_total(collector) == 4500.0
    assert landfilled == 1500.0


def test_landfill_branch_conserves_mass(ledger_waste_monitor):
    """A 100 m3 overflow takes the landfill branch: what fits is stored, the
    excess is landfilled and attributed."""
    collector, landfilled = _dispatch_all_vehicles(ledger_waste_monitor, {CONSTRUCTION: 4100.0})

    assert collector.collection_center.waste_storage_capacity == 4000.0
    assert stored_total(collector) == 4000.0
    assert landfilled == 100.0


def test_no_overflow_stores_everything(ledger_waste_monitor):
    """Within capacity, all waste is stored and nothing is landfilled."""
    collector, landfilled = _dispatch_all_vehicles(ledger_waste_monitor, {CONSTRUCTION: 300.0, PACKAGING: 200.0})

    assert stored_total(collector) == 500.0
    assert landfilled == 0.0
