"""The collector transport_costs series holds each trip once (T18).

It used to append the last trip cost on every daily sample, so one trip was
counted on its own day and again on every later day.
"""

import simpy

from instrumentation.waste_monitor import WasteMonitor
from models.enums import WasteType
from tests.core.factories import make_collector, make_generator_site


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def test_one_pickup_is_counted_once_across_daily_samples():
    env = simpy.Environment()
    monitor = WasteMonitor(env)
    collector = make_collector(env, monitor, waste_types=[PAPER])
    env.process(monitor.monitor_system_process([], [collector], []))
    collector.collect_from_generator(make_generator_site({PAPER: 10.0}))
    env.run(until=5)

    series = monitor.store.collection_history[collector.name]["transport_costs"]
    nonzero = [cost for cost in series if cost != 0.0]
    assert len(series) == 5
    assert len(nonzero) == 1, series
