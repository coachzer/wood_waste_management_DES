"""Treatment and collectors run on the daily operating clock (ADR 0020).

The region data sizes capacity per each entity's native period (treatment
``processing_time`` = 24 days, collector ``collection_frequency`` = 12 days).
Entities now act every OPERATING_TICK_DAYS on that period's per-tick share, so
annual capacity must be unchanged; a PULL operator must carry demand it could
not produce on the signal day forward instead of dropping it.
"""

from types import SimpleNamespace

import pytest
import simpy

import utils.capacity_utils as capacity_utils
from config.constants import (
    EXPANSION_SIZE_M3,
    OPERATING_TICK_DAYS,
    PROCESSING_CAPACITY_FRACTION,
    RECOVERING_BASE_EFFICIENCY,
    SIMULATION_DURATION,
)
from core.facility_builder import FacilityBuilder
from core.kanban_manager import KanbanManager
from core.transport_manager import PointToPointTransport
from models.enums import EntityStatus, InventoryPolicy, OutputType, RegionType, StockStrategy, WasteType
from models.state import SimulationState
from tests.core.factories import deterministic_scenario, make_collector, make_treatment
from utils.capacity_utils import handle_storage_event

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
TREATMENT_STORAGE_M3 = 24_000.0
PROCESSING_TIME_DAYS = 24
COLLECTION_CAPACITY_M3 = 80_000.0
COLLECTION_FREQUENCY_DAYS = 12


def _noop_monitor():
    noop = lambda *args, **kwargs: None
    return SimpleNamespace(
        update_entity_costs=noop,
        record_emission=noop,
        record_entity_status=noop,
        track_processing=noop,
        track_expansion=noop,
        record_landfill=noop,
    )


def _treatment(env, inventory_policy=InventoryPolicy.PUSH, state=None, kanban_manager=None):
    return make_treatment(
        env,
        _noop_monitor(),
        processing_time=PROCESSING_TIME_DAYS,
        waste_storage_capacity=TREATMENT_STORAGE_M3,
        kanban_manager=kanban_manager or KanbanManager(),
        finished_goods_capacity={OutputType.OSB: 10_000.0, OutputType.PARTICLE_BOARD: 10_000.0},
        initial_waste_storage={CONSTRUCTION: 20_000.0},
        order_share_by_waste_type={CONSTRUCTION: 1.0},
        order_up_to_level_m3=TREATMENT_STORAGE_M3,
        inventory_policy=inventory_policy,
        state=state or SimulationState(),
    )


def _collector(env, vehicle_capacity=None):
    return make_collector(
        env,
        _noop_monitor(),
        name="col-1",
        collection_capacity=COLLECTION_CAPACITY_M3,
        collection_frequency=COLLECTION_FREQUENCY_DAYS,
        transport_cost=50.0,
        vehicle_capacity=vehicle_capacity,
    )


def _annual(per_tick_capacity):
    return per_tick_capacity * SIMULATION_DURATION / OPERATING_TICK_DAYS


# --- annual capacity preservation --------------------------------------------


@pytest.mark.parametrize("tick_days", [1.0, 0.5])
def test_treatment_annual_capacity_equals_data_period_capacity(monkeypatch, tick_days):
    """per_tick * 365 / tick == storage * fraction * 365 / processing_time, at any tick.

    Mutation check (red): drop ``* OPERATING_TICK_DAYS / period_days`` from
    ``per_tick_capacity`` -> annual capacity is 24x (or 48x) too large.
    """
    monkeypatch.setattr(capacity_utils, "OPERATING_TICK_DAYS", tick_days)
    operator = _treatment(simpy.Environment())

    expected_annual = (
        TREATMENT_STORAGE_M3 * PROCESSING_CAPACITY_FRACTION * SIMULATION_DURATION / PROCESSING_TIME_DAYS
    )
    assert operator.processing_capacity_per_tick_m3 * SIMULATION_DURATION / tick_days == pytest.approx(expected_annual)


def test_treatment_capacity_unchanged_by_storage_expansion():
    """An EXPANSION_SIZE_M3 storage expansion does not raise processing capacity.

    Mutation check (red): derive processing capacity from the live
    ``waste_storage_capacity`` in ``_apply_status_throughput_effects`` ->
    capacity grows by 500 * fraction / 24 per expansion.
    """
    operator = _treatment(simpy.Environment())
    per_tick_before = operator.processing_capacity_per_tick_m3

    _cost, action = handle_storage_event(operator, {CONSTRUCTION: 10_000.0})
    operator._apply_status_throughput_effects()

    assert action == "expand_storage"
    assert operator.waste_storage_capacity == TREATMENT_STORAGE_M3 + EXPANSION_SIZE_M3
    assert operator.processing_capacity_per_tick_m3 == pytest.approx(per_tick_before)


def test_treatment_recovering_ramp_scales_the_per_tick_capacity():
    """RECOVERING runs at efficiency x the per-tick (not per-24-day) capacity."""
    operator = _treatment(simpy.Environment())
    per_tick = operator.initial_processing_capacity_per_tick_m3
    operator.status = EntityStatus.RECOVERING
    operator.recovery_progress = 0.5

    operator._apply_status_throughput_effects()

    ramp_efficiency = RECOVERING_BASE_EFFICIENCY + (1.0 - RECOVERING_BASE_EFFICIENCY) * 0.5
    assert operator.processing_capacity_per_tick_m3 == pytest.approx(per_tick * ramp_efficiency)


def test_collector_annual_capacity_equals_data_period_capacity():
    """Per-tick collection capacity * 365 equals 80,000 m3 per 12 days * 365.

    The collection center is a stock, so it keeps two data periods of capacity
    rather than shrinking with the tick.
    """
    collector = _collector(simpy.Environment())

    assert _annual(collector.initial_collection_capacity_per_tick_m3) == pytest.approx(
        COLLECTION_CAPACITY_M3 * SIMULATION_DURATION / COLLECTION_FREQUENCY_DAYS
    )
    assert collector.collection_center.waste_storage_capacity == 2 * COLLECTION_CAPACITY_M3


def test_builder_sets_vehicle_capacity_explicitly_to_one_tick_of_collection():
    """Each vehicle carries one tick of collection per trip, so one vehicle's
    annual throughput equals the collector's annual capacity.

    Mutation check (red): drop ``vehicle_capacity=`` from
    ``FacilityBuilder.create_collector`` and restore the old
    ``vehicle_capacity or collection_capacity`` fallback -> vehicles carry the
    raw 12-day volume.
    """
    env = simpy.Environment()
    state = SimulationState()
    builder = FacilityBuilder(
        env,
        facility_manager=None,
        waste_monitor=_noop_monitor(),
        scenario=deterministic_scenario(),
        transport_manager=PointToPointTransport(state=state, road_circuity_mean=1.0),
        kanban_manager=KanbanManager(),
        state=state,
        seed=1,
    )
    col_data = SimpleNamespace(
        id="col-1",
        waste_types=[CONSTRUCTION],
        collection_capacity=COLLECTION_CAPACITY_M3,
        collection_frequency=COLLECTION_FREQUENCY_DAYS,
        transport_cost=50.0,
        efficiency=1.0,
        availability=True,
    )
    collector = builder.create_collector(
        col_data, RegionType.PODRAVSKA, StockStrategy.REORDER_50, InventoryPolicy.PUSH
    )

    per_tick = COLLECTION_CAPACITY_M3 * OPERATING_TICK_DAYS / COLLECTION_FREQUENCY_DAYS
    assert [vehicle.capacity for vehicle in collector.vehicles] == [per_tick] * 3
    assert _annual(collector.vehicles[0].capacity) == pytest.approx(
        COLLECTION_CAPACITY_M3 * SIMULATION_DURATION / COLLECTION_FREQUENCY_DAYS
    )


# --- daily cadence ------------------------------------------------------------


def test_treatment_production_and_reorder_polling_run_every_tick():
    """Both treatment loops wake once per OPERATING_TICK_DAYS.

    Mutation check (red): yield ``self.processing_time`` in ``run_facility``
    or ``schedule_collection_requests`` -> wake-ups at 0 and 24 only.
    """
    env = simpy.Environment()
    operator = _treatment(env)
    production_times, reorder_times = [], []
    operator._process_available_waste = lambda: production_times.append(env.now)

    def record_reorder_poll():
        reorder_times.append(env.now)
        return {}

    operator._order_volumes_by_waste_type = record_reorder_poll

    env.run(until=10)

    assert production_times == [float(day) for day in range(10)]
    assert reorder_times == [float(day) for day in range(10)]


def test_collector_decides_every_tick_without_jitter():
    """The collector's collect decision runs daily, no uniform(1, 4) stretch.

    Mutation check (red): restore ``base + rng.uniform(1, 4)`` for the loop
    timeout -> 2-5 day gaps.
    """
    env = simpy.Environment()
    collector = _collector(env)
    decision_times = []

    def record_decision():
        decision_times.append(env.now)
        return False

    collector.should_collect = record_decision

    env.run(until=10.5)

    assert decision_times == [float(day) for day in range(1, 11)]


# --- PULL Production Backlog --------------------------------------------------


def _pull_operator_at_target(env):
    """A PULL operator whose finished goods are full, so its backlog is empty."""
    state = SimulationState()
    kanban_manager = KanbanManager()
    operator = _treatment(
        env, inventory_policy=InventoryPolicy.PULL, state=state, kanban_manager=kanban_manager
    )
    for output_type, capacity in operator.finished_goods.capacity.items():
        operator.finished_goods.current_storage[output_type] = capacity
    operator.pull_production_backlog_m3_by_product = dict.fromkeys(
        operator.pull_production_backlog_m3_by_product, 0.0
    )
    return operator, state, kanban_manager


def _sell_osb(operator, state, kanban_manager, attempted, consumed):
    """One market tick at day 0, as ``_market_consumption_process`` records it."""
    operator.finished_goods.current_storage[OutputType.OSB] -= consumed
    state.record_consumption_event(
        operator_name=operator.name,
        product="osb",
        attempted=attempted,
        consumed=consumed,
        reason="stockout" if consumed < attempted else None,
        timestamp=0.0,
    )
    kanban_manager.add_signal(
        waste_type=None, timestamp=0.0, volume=attempted, source_id=operator.name, source_type="market"
    )


def _pull_operator_with_one_week_of_osb_demand(env, attempted):
    operator, state, kanban_manager = _pull_operator_at_target(env)
    _sell_osb(operator, state, kanban_manager, attempted, consumed=attempted)
    return operator, state


def test_pull_week_of_demand_on_one_day_is_produced_over_later_ticks():
    """A week's OSB demand larger than one tick's capacity is fully produced.

    Day 0 alone cannot cover it (one tick of capacity); the rest is carried as
    backlog and produced on later ticks. The backlog never adds a Consumption
    Event, so Lost Sales and Service Level stay defined by the market log.

    Mutation check (red): zero the backlog after each tick's production
    (``self.pull_production_backlog_m3_by_product[product] = 0.0``) -> only day 0's output.
    """
    env = simpy.Environment()
    one_tick_output = (
        TREATMENT_STORAGE_M3 * PROCESSING_CAPACITY_FRACTION * OPERATING_TICK_DAYS / PROCESSING_TIME_DAYS
    ) * 0.98  # construction wood -> OSB conversion efficiency
    attempted = 4.5 * one_tick_output
    operator, state = _pull_operator_with_one_week_of_osb_demand(env, attempted)

    env.run(until=1)
    produced_on_signal_day = operator.product_volumes["osb"]
    env.run(until=14)

    assert produced_on_signal_day == pytest.approx(one_tick_output)
    assert operator.product_volumes["osb"] == pytest.approx(attempted)
    assert operator.pull_production_backlog_m3_by_product["osb"] == pytest.approx(0.0, abs=1e-6)
    assert len(state.consumption_events) == 1


def test_pull_operator_absorbs_market_signal_while_failed():
    """A signal that arrives during an outage is still produced after it.

    The outage (3 days) outlives KANBAN_SIGNAL_MAX_AGE_DAYS (1 day), so the
    signal is pruned before the operator produces again; the demand survives
    only because FAILED ticks still absorb signals into the backlog.

    Mutation check (red): move ``_absorb_market_signals`` below the FAILED
    early-continue in ``run_facility`` -> nothing is ever produced.
    """
    env = simpy.Environment()
    operator, _state = _pull_operator_with_one_week_of_osb_demand(env, attempted=500.0)
    operator.status = EntityStatus.FAILED

    def restore_after_outage():
        yield env.timeout(3)
        operator.status = EntityStatus.OPERATIONAL

    env.process(restore_after_outage())
    env.run(until=3)
    assert operator.product_volumes["osb"] == 0.0

    env.run(until=6)
    assert operator.product_volumes["osb"] == pytest.approx(500.0)


def test_pull_backlog_starts_at_the_finished_goods_gap():
    """Finished goods start half-full; the backlog holds the other half (ADR 0029).

    Mutation check (red): start the backlog empty -> nothing is produced without a sale.
    """
    env = simpy.Environment()
    operator = _treatment(env, inventory_policy=InventoryPolicy.PULL, kanban_manager=KanbanManager())

    env.run(until=60)

    for output_type, capacity in operator.finished_goods.capacity.items():
        assert operator.finished_goods.current_storage[output_type] == pytest.approx(capacity)
        assert operator.pull_production_backlog_m3_by_product[output_type.value] == pytest.approx(0.0, abs=1e-6)


def test_pull_backlog_replaces_what_was_sold_not_what_was_asked():
    """A lost sale does not come back, so only the consumed volume is remade (ADR 0029).

    Mutation check (red): add ``event["attempted"]`` in ``_absorb_market_signals`` ->
    the 300 m3 that was never sold sticks in the backlog.
    """
    env = simpy.Environment()
    operator, state, kanban_manager = _pull_operator_at_target(env)
    _sell_osb(operator, state, kanban_manager, attempted=500.0, consumed=200.0)

    env.run(until=14)

    assert operator.product_volumes["osb"] == pytest.approx(200.0)
    assert operator.pull_production_backlog_m3_by_product["osb"] == pytest.approx(0.0, abs=1e-6)
