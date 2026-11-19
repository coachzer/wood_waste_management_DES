"""Collector efficiency is applied to collection capacity exactly once.

``collection_loop`` already sets ``collection_capacity_per_tick_m3`` from ``initial x efficiency``.
Consumers used to multiply by ``efficiency`` again, so effective capacity scaled
with efficiency squared and amplified the policy-dependent efficiency curves.
"""

import simpy

from tests.core.factories import make_collector, make_generator_site
from models.enums import WasteType

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01


def test_site_pickup_is_capped_by_scaled_capacity_not_its_square(ledger_waste_monitor):
    """At the 0.5 efficiency floor the loop sets capacity 50; a pickup takes 50, not 25.

    Aging (``update_efficiency``) reaches the floor by day 1000, so the clock is
    run there and ``collection_loop`` derives the capacity itself. A same-region
    round trip takes under an hour, so the pickup lands inside the tick.

    Mutation check (red): restore ``self.collection_capacity_per_tick_m3 * self.efficiency``
    in the site pickup -> the pickup is 25.
    """
    env = simpy.Environment()
    collector = make_collector(env, ledger_waste_monitor, collection_capacity=100.0, collection_frequency=1)
    generator = make_generator_site({CONSTRUCTION: 1000.0})
    env.run(until=1000.5)

    collector.collect_from_generator(generator)
    env.run(until=1000.9)

    assert collector.efficiency == 0.5
    assert collector.collection_center.current_storage[CONSTRUCTION] == 50.0
    assert generator.current_storage == 950.0
