"""Collectors serve treatment signals first, largest first, newest per operator and type (ADR 0031)."""
from types import SimpleNamespace

from core.collector import CollectorCompany
from core.kanban_manager import KanbanManager
from models.data_classes import WasteStream
from models.enums import RegionType, WasteType

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
BARK = WasteType.BARK_CORK_WASTE_03_01_01


class OneVehicleCollector:
    """Calls the real dispatch loop unbound; records each pickup and has one vehicle."""

    _signals_in_dispatch_order = CollectorCompany._signals_in_dispatch_order

    def __init__(self, kanban_manager):
        self.region_type = RegionType.GORENJSKA
        self.kanban_manager = kanban_manager
        self.env = SimpleNamespace(now=2.0)
        self.vehicles_left = 1
        self.pickups = []
        self.generator = SimpleNamespace(
            name="gen_gorenjska",
            waste_streams={
                SAWDUST: WasteStream(waste_type=SAWDUST, volume=500.0),
                BARK: WasteStream(waste_type=BARK, volume=500.0),
            },
        )

    def _get_prioritized_generators(self):
        return [self.generator]

    def _find_available_vehicle(self):
        return self.vehicles_left > 0

    def collect_from_generator(self, generator, requested_volume=None, waste_type=None):
        self.vehicles_left -= 1
        self.pickups.append((waste_type, requested_volume))

    def _propagate_signal_to_generators(self, signal, current_time):
        pass


def _treatment_signal(kanban_manager, waste_type, volume, timestamp=2.0):
    kanban_manager.add_signal(
        waste_type=waste_type, timestamp=timestamp, volume=volume,
        source_id="proc_gorenjska", source_type="treatment", target_region=RegionType.GORENJSKA,
    )


def _dispatch(kanban_manager):
    collector = OneVehicleCollector(kanban_manager)
    CollectorCompany._process_kanban_signals(collector, kanban_manager.get_signals(2.0))
    return collector.pickups


def test_largest_treatment_order_gets_the_last_vehicle():
    """Mutation check (red): keep signals in posting order."""
    kanban_manager = KanbanManager()
    _treatment_signal(kanban_manager, BARK, 0.02)
    _treatment_signal(kanban_manager, SAWDUST, 300.0)

    assert _dispatch(kanban_manager) == [(SAWDUST, 300.0)]


def test_treatment_order_beats_a_larger_generator_signal():
    """Mutation check (red): sort all signals by volume alone."""
    kanban_manager = KanbanManager()
    kanban_manager.add_signal(
        waste_type=BARK, timestamp=2.0, volume=450.0, source_id="gen_gorenjska", source_type="generator",
    )
    _treatment_signal(kanban_manager, SAWDUST, 10.0)

    assert _dispatch(kanban_manager) == [(SAWDUST, 10.0)]


def test_only_the_newest_order_per_operator_and_type_is_live():
    """Mutation check (red): sum duplicate orders instead of keeping the newest."""
    kanban_manager = KanbanManager()
    _treatment_signal(kanban_manager, SAWDUST, 300.0, timestamp=1.0)
    _treatment_signal(kanban_manager, SAWDUST, 120.0, timestamp=2.0)

    assert _dispatch(kanban_manager) == [(SAWDUST, 120.0)]
    assert kanban_manager.get_signals(2.0) == []
