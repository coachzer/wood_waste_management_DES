"""Treatment intake conserves mass on overflow (T4).

The expand branch used to grow capacity but store only the pre-expansion
headroom, so the overflow was neither stored nor landfilled.
"""

import simpy

from models.enums import WasteType
from tests.core.factories import make_treatment


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def _intake(monitor, capacity, volume):
    treatment = make_treatment(
        simpy.Environment(), monitor,
        waste_storage_capacity=capacity, initial_waste_storage={PAPER: 0.0},
        order_share_by_waste_type={PAPER: 1.0}, order_up_to_level_m3=100.0,
    )
    stored = treatment._add_to_storage({PAPER: volume})
    landfilled = monitor.store.landfilled_volume_by_entity().get(treatment.name, 0.0)
    return treatment, stored, landfilled


def test_expand_branch_stores_overflow_and_landfills_remainder(ledger_waste_monitor):
    """6000 m3 into an empty 4000 m3 store overflows by 2000 (expand at PAPER
    density): capacity grows by 500, 4500 is stored, 1500 landfilled."""
    treatment, stored, landfilled = _intake(ledger_waste_monitor, 4000.0, 6000.0)

    assert treatment.waste_storage_capacity == 4500.0
    assert stored == 4500.0
    assert treatment.current_storage == 4500.0
    assert landfilled == 1500.0


def test_landfill_branch_conserves_mass(ledger_waste_monitor):
    """A 100 m3 overflow is cheaper to landfill: 4000 stored, 100 landfilled."""
    treatment, stored, landfilled = _intake(ledger_waste_monitor, 4000.0, 4100.0)

    assert treatment.waste_storage_capacity == 4000.0
    assert stored == 4000.0
    assert landfilled == 100.0
