"""Tests for treatment kanban signal region routing (plan 008 / ADR 0018).

Treatment signals carry a target_region so that only the collector in the
operator's own region reads and acknowledges them.  Every other PULL collector
on the shared bus must skip them and leave them for the intended recipient.
Signals without a target_region (generator-sourced) pass through any region, and a
collector that cannot serve one leaves it on the bus for one that can.
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

    _signals_in_dispatch_order = CollectorCompany._signals_in_dispatch_order

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


class ServingCollector(FakeCollector):
    """A collector whose prioritized generators include the signalling generator."""

    def __init__(self, region_type, kanban_manager, generator):
        super().__init__(region_type, kanban_manager)
        self.generator = generator
        self.collected_from = []

    def _get_prioritized_generators(self):
        return [self.generator]

    def _find_available_vehicle(self):
        return True

    def collect_from_generator(self, generator, requested_volume=None, waste_type=None):
        self.collected_from.append(generator.name)


def _generator(name, region_type):
    return SimpleNamespace(
        name=name, region_type=region_type, waste_streams={WASTE: SimpleNamespace(volume=50.0)}
    )


def _bus_with_generator_signal():
    km = KanbanManager()
    km.add_signal(waste_type=WASTE, timestamp=1.0, volume=100,
                  source_id="gen-1", source_type="generator")
    return km


def test_unaddressed_signal_reaches_a_collector_in_another_region():
    km = _bus_with_generator_signal()
    collector = ServingCollector(RegionType.GORENJSKA, km, _generator("gen-1", RegionType.PODRAVSKA))

    CollectorCompany._process_kanban_signals(collector, _pending_non_market(km))

    assert collector.collected_from == ["gen-1"]
    assert _pending_non_market(km) == []


def test_collector_that_cannot_serve_a_generator_signal_leaves_it_on_the_bus():
    km = _bus_with_generator_signal()
    remote = FakeCollector(RegionType.GORENJSKA, km)

    CollectorCompany._process_kanban_signals(remote, _pending_non_market(km))

    assert len(_pending_non_market(km)) == 1


def test_generator_signal_left_by_a_remote_collector_is_served_by_the_local_one():
    km = _bus_with_generator_signal()
    remote = FakeCollector(RegionType.GORENJSKA, km)
    local = ServingCollector(RegionType.PODRAVSKA, km, _generator("gen-1", RegionType.PODRAVSKA))

    CollectorCompany._process_kanban_signals(remote, _pending_non_market(km))
    CollectorCompany._process_kanban_signals(local, _pending_non_market(km))

    assert local.collected_from == ["gen-1"]
