"""Tests for treatment kanban signal region routing (plan 008 / ADR 0018).

Treatment signals carry a target_region so that only the collector in the
operator's own region reads and acknowledges them.  Every other PULL collector
on the shared bus must skip them and leave them for the intended recipient.
Signals without a target_region (generator-sourced) pass through any region.
"""
from types import SimpleNamespace

from core.collector import CollectorCompany
from core.kanban_manager import KanbanManager
from models.enums import RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


class FakeCollector:
    """Minimal stand-in for CollectorCompany._process_kanban_signals.

    The method is called unbound -- CollectorCompany._process_kanban_signals(fake, ...)
    -- so self resolves to this FakeCollector and self._propagate_signal_to_generators
    resolves to the stub below (not the real method that needs self.state).
    """

    def __init__(self, region_type, kanban_manager):
        self.region_type = region_type
        self.kanban_manager = kanban_manager
        self.env = SimpleNamespace(now=1.0)

    def _get_prioritized_generators(self):
        return []

    def _propagate_signal_to_generators(self, signal, current_time):
        pass  # stub: the real one reads self.state, which we do not provide


def _pending_non_market(km):
    """Non-acknowledged, non-market signals still on the bus."""
    return [s for s in km.get_signals(1.0) if s.get('source_type') != "market"]


def test_wrong_region_collector_does_not_consume_treatment_signal():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="treatment-A", source_type="treatment",
                  target_region=RegionType.PODRAVSKA)
    wrong = FakeCollector(RegionType.GORENJSKA, km)

    CollectorCompany._process_kanban_signals(wrong, _pending_non_market(km))

    assert len(_pending_non_market(km)) == 1, \
        "wrong-region collector must leave the signal on the bus"


def test_right_region_collector_consumes_treatment_signal():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="treatment-A", source_type="treatment",
                  target_region=RegionType.PODRAVSKA)
    right = FakeCollector(RegionType.PODRAVSKA, km)

    CollectorCompany._process_kanban_signals(right, _pending_non_market(km))

    assert _pending_non_market(km) == [], \
        "right-region collector should propagate upstream and ack"


def test_unaddressed_signal_passes_through_any_region():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="gen-1", source_type="generator")  # target_region defaults to None
    collector = FakeCollector(RegionType.GORENJSKA, km)

    CollectorCompany._process_kanban_signals(collector, _pending_non_market(km))

    assert _pending_non_market(km) == [], \
        "an unaddressed signal must not be blocked by the region filter"
