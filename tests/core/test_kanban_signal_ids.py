"""One operator's local and surplus-region signals are separate signals (T26).

Both copies used to share id f"{source_id}_{waste_type}_{timestamp}", so the
surplus collector acknowledging its copy hid the local one on the shared bus.
"""

from core.kanban_manager import KanbanManager
from models.enums import RegionType, WasteType


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def _post(bus, target_region, volume):
    bus.add_signal(waste_type=PAPER, timestamp=3, volume=volume, source_id="proc-1",
                   source_type="treatment", target_region=target_region)


def test_acknowledging_one_regions_copy_keeps_the_other():
    bus = KanbanManager()
    _post(bus, RegionType.PODRAVSKA, 100.0)
    _post(bus, RegionType.GORENJSKA, 40.0)

    surplus_copy = next(s for s in bus.get_signals() if s["target_region"] == RegionType.GORENJSKA)
    bus.acknowledge_signal(surplus_copy["id"])

    assert [s["target_region"] for s in bus.get_signals()] == [RegionType.PODRAVSKA]


def test_reposting_an_acknowledged_signal_stays_suppressed():
    bus = KanbanManager()
    _post(bus, RegionType.PODRAVSKA, 100.0)
    bus.acknowledge_signal(bus.get_signals()[0]["id"])
    _post(bus, RegionType.PODRAVSKA, 100.0)

    assert bus.get_signals() == []


def test_reposting_an_active_signal_keeps_one_copy():
    bus = KanbanManager()
    _post(bus, RegionType.PODRAVSKA, 100.0)
    _post(bus, RegionType.PODRAVSKA, 100.0)

    assert len(bus.get_signals()) == 1
