"""Treatment orders each input type against its own level (ADR 0026)."""
from types import SimpleNamespace

import pytest
import simpy

from core.facility_builder import FacilityBuilder
from models.enums import OutputType, RegionType, StockStrategy, WasteType
from models.state import SimulationState
from tests.core.factories import make_collector, make_treatment, posted_treatment_orders
from models.transformations import volumetric_yield

EARLY_TYPE = WasteType.CONSTRUCTION_WOOD_17_02_01
LATE_TYPE = sorted(WasteType, key=lambda waste_type: waste_type.value)[-1]
ORDER_UP_TO_LEVEL_M3 = 1_000.0
STORAGE_CAPACITY_M3 = 100 * ORDER_UP_TO_LEVEL_M3




@pytest.mark.parametrize("strategy,late_on_hand,orders_late", [
    (StockStrategy.ON_DEMAND, 499.0, True),
    (StockStrategy.REORDER_90, 460.0, False),
    (StockStrategy.REORDER_90, 440.0, True),
    (StockStrategy.REORDER_50, 260.0, False),
    (StockStrategy.REORDER_50, 240.0, True),
])
def test_each_type_reorders_below_the_strategy_fraction_of_its_own_level(
    noop_waste_monitor, strategy, late_on_hand, orders_late
):
    # The early type is far over its level, so total storage is above every
    # total-based reorder point; only a per-type trigger orders the late type.
    # Storage capacity is 100 times S, so levels taken from capacity order every
    # case.
    orders = posted_treatment_orders(
        noop_waste_monitor, strategy,
        on_hand={EARLY_TYPE: 900.0, LATE_TYPE: late_on_hand},
        order_share_by_waste_type={EARLY_TYPE: 0.5, LATE_TYPE: 0.5},
        order_up_to_level_m3=ORDER_UP_TO_LEVEL_M3,
        waste_storage_capacity=STORAGE_CAPACITY_M3,
    )

    assert EARLY_TYPE not in orders
    if orders_late:
        assert orders == {LATE_TYPE: pytest.approx(500.0 - late_on_hand)}
    else:
        assert orders == {}


def test_late_sorted_type_is_collected_when_an_early_type_has_plenty(ledger_waste_monitor):
    # One collector holds both types. A single all-type request would be filled
    # by the early type alone.
    env = simpy.Environment()
    state = SimulationState()
    collector = make_collector(env, ledger_waste_monitor, state=state, waste_types=[EARLY_TYPE, LATE_TYPE])
    collector.collection_center.current_storage.update({EARLY_TYPE: 10_000.0, LATE_TYPE: 10_000.0})
    state.collectors = [collector]
    operator = make_treatment(
        env, ledger_waste_monitor, state=state, transformations={},
        order_share_by_waste_type={EARLY_TYPE: 0.5, LATE_TYPE: 0.5},
        order_up_to_level_m3=ORDER_UP_TO_LEVEL_M3,
    )

    operator.trigger_collection({EARLY_TYPE: 100.0, LATE_TYPE: 100.0})

    assert operator.waste_storage[EARLY_TYPE] == 100.0
    assert operator.waste_storage[LATE_TYPE] == 100.0


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

    # Need is demand / mean volumetric yield of the product's routes (ADR 0043). OSB's need is
    # split 3:1 by the mix; MDF's need goes to LATE_TYPE only.
    osb_need = 300.0 / ((volumetric_yield(0.5, EARLY_TYPE, OutputType.OSB) + volumetric_yield(0.5, LATE_TYPE, OutputType.OSB)) / 2)
    mdf_need = 100.0 / volumetric_yield(0.5, LATE_TYPE, OutputType.MDF)
    osb_fraction = osb_need / (osb_need + mdf_need)
    assert shares == {
        EARLY_TYPE: pytest.approx(osb_fraction * 0.75),
        LATE_TYPE: pytest.approx(osb_fraction * 0.25 + (1 - osb_fraction)),
    }
