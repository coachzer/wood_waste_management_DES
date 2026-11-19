"""Collector efficiency is applied to collection capacity exactly once.

``collection_loop`` already stores ``collection_capacity = initial x efficiency``.
Consumers used to multiply by ``efficiency`` again, so effective capacity scaled
with efficiency squared and amplified the policy-dependent efficiency curves.
"""

from types import SimpleNamespace

import simpy

from tests.core.factories import make_collector
from models.data_classes import WasteStream
from models.enums import WasteType

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01


def _collector(noop_waste_monitor):
    return make_collector(simpy.Environment(), noop_waste_monitor)


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
