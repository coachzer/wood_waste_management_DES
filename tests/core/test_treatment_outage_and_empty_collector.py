"""A FAILED operator stops ordering, and an empty collector still hears demand.

Two defects found auditing PUSH vs PULL: ``schedule_collection_requests`` kept
ordering waste while the operator was FAILED, and
``_propagate_signal_to_collectors`` skipped collectors holding none of the waste
type, which are the ones that must pass demand on to generators.
"""

from types import SimpleNamespace

import simpy

from core.kanban_manager import KanbanManager
from models.enums import EntityStatus, InventoryPolicy, RegionType
from models.state import SimulationState
from tests.core.test_operating_clock import CONSTRUCTION, _treatment


def _count_collection_calls(operator, env, days):
    calls = []
    operator._order_volumes_by_waste_type = lambda: {CONSTRUCTION: 10.0}
    operator.trigger_collection = lambda order_volumes: calls.append(env.now)
    env.run(until=days)
    return calls


def test_operational_operator_orders_waste_each_tick():
    """Control for the FAILED test, so a vacuous pass is impossible."""
    env = simpy.Environment()
    operator = _treatment(env)

    assert len(_count_collection_calls(operator, env, 5)) == 5


def test_failed_operator_does_not_order_waste():
    """Mutation check (red): drop the FAILED guard in ``schedule_collection_requests``
    -> five collection calls during the outage."""
    env = simpy.Environment()
    operator = _treatment(env)
    operator.status = EntityStatus.FAILED

    assert _count_collection_calls(operator, env, 5) == []


def _fake_collector(region, stock):
    return SimpleNamespace(
        region_type=region,
        is_operational=True,
        inventory_policy=SimpleNamespace(is_pull=lambda: True),
        collection_center=SimpleNamespace(current_storage=dict(stock)),
        kanban_manager=KanbanManager(),
    )


def test_empty_local_collector_receives_treatment_signal():
    """Mutation check (red): restore the ``current_storage > 0`` filter -> no signal.
    """
    env = simpy.Environment()
    state = SimulationState()
    operator = _treatment(env, inventory_policy=InventoryPolicy.PULL, state=state)
    empty = _fake_collector(operator.region_type, {})
    state.collectors = [empty]

    operator._propagate_signal_to_collectors(CONSTRUCTION, 100.0, 1.0)

    signals = empty.kanban_manager.get_signals()
    assert [(s["source_type"], s["volume"]) for s in signals] == [("treatment", 100.0)]


def test_other_region_collector_gets_no_treatment_signal():
    env = simpy.Environment()
    state = SimulationState()
    operator = _treatment(env, inventory_policy=InventoryPolicy.PULL, state=state)
    other_region = next(r for r in RegionType if r != operator.region_type)
    elsewhere = _fake_collector(other_region, {CONSTRUCTION: 500.0})
    state.collectors = [elsewhere]

    operator._propagate_signal_to_collectors(CONSTRUCTION, 100.0, 1.0)

    assert elsewhere.kanban_manager.get_signals() == []
