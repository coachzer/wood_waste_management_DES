"""Treatment orders each input type against its own level (ADR 0026)."""
from types import SimpleNamespace

import pytest
import simpy

from core.facility_builder import FacilityBuilder
from core.strategies.stock_strategy import build_stock_strategy
from core.treatment import TreatmentOperator
from models.enums import OutputType, RegionType, StockStrategy, WasteType
from models.state import SimulationState
from tests.core.test_operating_clock import _treatment

EARLY_TYPE = WasteType.CONSTRUCTION_WOOD_17_02_01
LATE_TYPE = sorted(WasteType, key=lambda waste_type: waste_type.value)[-1]
ORDER_UP_TO_LEVEL_M3 = 1_000.0
STORAGE_CAPACITY_M3 = 100 * ORDER_UP_TO_LEVEL_M3


def _operator(strategy, on_hand):
    return SimpleNamespace(
        waste_storage=dict(on_hand),
        waste_storage_capacity=STORAGE_CAPACITY_M3,
        order_up_to_level_m3=ORDER_UP_TO_LEVEL_M3,
        order_share_by_waste_type={EARLY_TYPE: 0.5, LATE_TYPE: 0.5},
        stock_strategy_behavior=build_stock_strategy(strategy),
    )


@pytest.mark.parametrize("strategy,late_on_hand,orders_late", [
    (StockStrategy.ON_DEMAND, 499.0, True),
    (StockStrategy.REORDER_90, 460.0, False),
    (StockStrategy.REORDER_90, 440.0, True),
    (StockStrategy.REORDER_50, 260.0, False),
    (StockStrategy.REORDER_50, 240.0, True),
])
def test_each_type_reorders_below_the_strategy_fraction_of_its_own_level(strategy, late_on_hand, orders_late):
    # The early type is far over its level, so total storage is above every
    # total-based reorder point; only a per-type trigger orders the late type.
    # Storage capacity is 100 times S, so levels taken from capacity order every
    # case.
    operator = _operator(strategy, {EARLY_TYPE: 900.0, LATE_TYPE: late_on_hand})

    orders = TreatmentOperator._order_volumes_by_waste_type(operator)

    assert EARLY_TYPE not in orders
    if orders_late:
        assert orders == {LATE_TYPE: pytest.approx(500.0 - late_on_hand)}
    else:
        assert orders == {}


def test_late_sorted_type_is_collected_when_an_early_type_has_plenty():
    # One collector holds both types. A single all-type request would be filled
    # by the early type alone.
    env = simpy.Environment()
    state = SimulationState()
    operator = _treatment(env, state=state)
    operator._waste_storage = dict.fromkeys(WasteType, 0.0)
    stock = {EARLY_TYPE: 10_000.0, LATE_TYPE: 10_000.0}

    def provide_waste_for_treatment(requested_amount, needed_types, treatment_name=None):
        drained = {}
        for waste_type in needed_types:
            take = min(stock[waste_type], requested_amount)
            stock[waste_type] -= take
            requested_amount -= take
            if take > 0:
                drained[waste_type] = take
        return drained

    state.collectors = [SimpleNamespace(
        region_type=operator.region_type, is_operational=True,
        provide_waste_for_treatment=provide_waste_for_treatment,
        collection_center=SimpleNamespace(current_storage=dict.fromkeys(WasteType, 0.0)),
    )]

    operator.trigger_collection({EARLY_TYPE: 100.0, LATE_TYPE: 100.0})

    assert operator.waste_storage[LATE_TYPE] > 0


def test_order_shares_follow_product_need_and_national_mix():
    builder = FacilityBuilder.__new__(FacilityBuilder)
    builder.facility_manager = SimpleNamespace(demand={"osb": 300.0, "mdf": 100.0})
    # Only one region generates anything, so the national mix is 3:1.
    builder._region_generation_volume = lambda region: (
        {EARLY_TYPE: 3.0, LATE_TYPE: 1.0} if region == RegionType.PODRAVSKA else {}
    )
    route = lambda input_type, output_type: SimpleNamespace(
        input_type=input_type, output_type=output_type, conversion_efficiency=0.5
    )
    transformations = {
        1: route(EARLY_TYPE, OutputType.OSB),
        2: route(LATE_TYPE, OutputType.OSB),
        3: route(LATE_TYPE, OutputType.MDF),
    }

    shares = builder._order_share_by_waste_type(transformations)

    # OSB is 3/4 of the need, split 3:1 by the mix; MDF's 1/4 goes to LATE_TYPE only.
    assert shares == {EARLY_TYPE: pytest.approx(0.75 * 0.75), LATE_TYPE: pytest.approx(0.75 * 0.25 + 0.25)}
