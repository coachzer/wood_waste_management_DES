"""Collector efficiency is applied to collection capacity exactly once.

``collection_loop`` already stores ``collection_capacity = initial x efficiency``.
Consumers used to multiply by ``efficiency`` again, so effective capacity scaled
with efficiency squared and amplified the policy-dependent efficiency curves.
"""

from types import SimpleNamespace

import simpy

from core.collector import CollectorCompany
from models.data_classes import WasteStream
from models.enums import InventoryPolicy, StockStrategy, WasteType
from models.state import SimulationState

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01


def _collector(noop_waste_monitor):
    return CollectorCompany(
        env=simpy.Environment(),
        name="collector-1",
        waste_types=[CONSTRUCTION],
        collection_capacity=100.0,
        collection_frequency=12,
        transport_cost=10.0,
        efficiency=1.0,
        region="podravska",
        waste_monitor=noop_waste_monitor,
        inventory_policy=InventoryPolicy.PUSH,
        stock_strategy=StockStrategy.REORDER_50,
        state=SimulationState(),
    )


def test_site_pickup_is_capped_by_scaled_capacity_not_its_square(noop_waste_monitor):
    """With efficiency 0.5 the loop sets capacity 50; a pickup takes 50, not 25.

    Mutation check (red): restore ``self.collection_capacity_per_tick_m3 * self.efficiency``
    in ``_perform_collection_at_site`` -> the pickup is 25.
    """
    collector = _collector(noop_waste_monitor)
    collector.efficiency = 0.5
    collector.collection_capacity_per_tick_m3 = 100.0 * collector.efficiency  # as collection_loop sets it

    generator = SimpleNamespace(
        name="generator-1",
        waste_streams={CONSTRUCTION: WasteStream(waste_type=CONSTRUCTION, volume=1000.0)},
        current_storage=1000.0,
    )

    collected, _ = collector._perform_collection_at_site(generator, target_volume=1000.0)

    assert collected == 50.0
