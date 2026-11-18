"""Treatment order-up-to level S is sized from demand, not storage capacity (ADR 0027)."""
import math
from types import SimpleNamespace

import pytest

from config.constants import SAFETY_STOCK_Z, WEEKS_PER_YEAR
from core.facility_builder import FacilityBuilder
from core.strategies.stock_strategy import build_stock_strategy
from core.treatment import TreatmentOperator
from models.enums import OutputType, StockStrategy, WasteType
from utils.seasonality import seasonal_factor_standard_deviation

ORDER_UP_TO_LEVEL_M3 = 1_000.0
STORAGE_CAPACITY_M3 = 100_000.0


def _builder(demand):
    builder = FacilityBuilder.__new__(FacilityBuilder)
    builder.facility_manager = SimpleNamespace(demand=demand)
    return builder


def _transformation(output_type, efficiency):
    return SimpleNamespace(output_type=output_type, conversion_efficiency=efficiency)


def test_order_up_to_level_is_one_interval_of_waste_plus_seasonal_safety_stock():
    builder = _builder({"osb": 5_200.0, "mdf": 1_000_000.0})
    transformations = {"a": _transformation(OutputType.OSB, 0.8), "b": _transformation(OutputType.OSB, 0.6)}

    level = builder._order_up_to_level(transformations, market_share=0.5, waste_storage_capacity=STORAGE_CAPACITY_M3)

    waste_per_interval = 0.5 * (5_200.0 / WEEKS_PER_YEAR) / 0.7
    expected = waste_per_interval * (1 + SAFETY_STOCK_Z * seasonal_factor_standard_deviation())
    assert level == pytest.approx(expected)
    assert seasonal_factor_standard_deviation() == pytest.approx(0.2 / math.sqrt(2))


def test_order_up_to_level_is_clamped_at_storage_capacity():
    builder = _builder({"osb": 1e9})
    level = builder._order_up_to_level(
        {"a": _transformation(OutputType.OSB, 0.8)}, market_share=1.0, waste_storage_capacity=500.0
    )
    assert level == 500.0


def test_on_demand_orders_back_exactly_what_was_consumed():
    operator = SimpleNamespace(
        waste_storage={WasteType.CONSTRUCTION_WOOD_17_02_01: ORDER_UP_TO_LEVEL_M3 - 37.0},
        waste_storage_capacity=STORAGE_CAPACITY_M3,
        order_up_to_level_m3=ORDER_UP_TO_LEVEL_M3,
        order_share_by_waste_type={WasteType.CONSTRUCTION_WOOD_17_02_01: 1.0},
        stock_strategy_behavior=build_stock_strategy(StockStrategy.ON_DEMAND),
    )
    orders = TreatmentOperator._order_volumes_by_waste_type(operator)
    assert orders == {WasteType.CONSTRUCTION_WOOD_17_02_01: pytest.approx(37.0)}
