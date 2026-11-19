"""A FAILED operator stops ordering, and an empty collector still hears demand.

Two defects found auditing PUSH vs PULL: ``schedule_collection_requests`` kept
ordering waste while the operator was FAILED, and the treatment signal skipped
collectors holding none of the waste type, which are the ones that must pass
demand on to generators.

The operator is real and runs its own order tick. Collectors are passive
stand-ins that only record the signals they receive and supply nothing.
"""

from models.enums import EntityStatus, RegionType, WasteType
from tests.core.factories import (
    EMPTY_PULL_OPERATOR_ORDER_M3,
    run_empty_pull_operator,
    signal_recording_collector,
)

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01


def test_operational_operator_orders_waste_each_tick(noop_waste_monitor):
    """Control for the FAILED test, so a vacuous pass is impossible."""
    local = signal_recording_collector(RegionType.PODRAVSKA, {})
    run_empty_pull_operator(noop_waste_monitor, [local], days=5)

    assert local.kanban_manager.posted_timestamps == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_failed_operator_does_not_order_waste(noop_waste_monitor):
    """Mutation check (red): drop the FAILED guard in ``schedule_collection_requests``
    -> five orders during the outage."""
    local = signal_recording_collector(RegionType.PODRAVSKA, {})
    run_empty_pull_operator(noop_waste_monitor, [local], days=5, status=EntityStatus.FAILED)

    assert local.kanban_manager.posted_timestamps == []


def test_empty_local_collector_receives_treatment_signal(noop_waste_monitor):
    """Mutation check (red): restore the ``current_storage > 0`` filter -> no signal."""
    empty = signal_recording_collector(RegionType.PODRAVSKA, {})
    run_empty_pull_operator(noop_waste_monitor, [empty])

    signals = empty.kanban_manager.get_signals()
    assert [(s["source_type"], s["volume"]) for s in signals] == [("treatment", EMPTY_PULL_OPERATOR_ORDER_M3)]


def test_other_region_collector_gets_no_treatment_signal(noop_waste_monitor):
    other_region = next(region for region in RegionType if region != RegionType.PODRAVSKA)
    elsewhere = signal_recording_collector(other_region, {CONSTRUCTION: 500.0})
    run_empty_pull_operator(noop_waste_monitor, [elsewhere])

    assert elsewhere.kanban_manager.get_signals() == []
