"""Status is sampled once per day, by the daily monitor poll only (T36)."""

import simpy

from core.treatment import DirectRequest
from instrumentation.waste_monitor import WasteMonitor
from models.enums import WasteType
from tests.core.factories import make_collector, make_treatment


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def test_same_day_calls_record_one_status_sample():
    monitor = WasteMonitor()
    treatment = make_treatment(
        simpy.Environment(), monitor, initial_waste_storage={PAPER: 0.0},
        order_share_by_waste_type={PAPER: 1.0}, order_up_to_level_m3=100.0,
    )

    for timestamp in (0, 0, 1, 1, 2):
        monitor.track_processing(treatment, timestamp)

    status_history = monitor.store.entity_status_history["treatments"][treatment.name]
    assert status_history["timestamps"] == [0, 1, 2]
    assert len(status_history["status"]) == 3


def test_failure_transitions_add_no_status_samples():
    """The status history is the daily poll only; a failure day is not sampled twice.

    Failure transitions used to append their own sample on the polled day,
    which pulled availability toward FAILED/RECOVERING days.
    """
    env = simpy.Environment()
    monitor = WasteMonitor(env)
    collector = make_collector(env, monitor)
    env.process(monitor.monitor_system_process([], [collector], []))

    def fail_on_day_two():
        yield env.timeout(2)
        collector.check_failure(env.now, failure_probability=1.0)

    env.process(fail_on_day_two())
    env.run(until=5)

    status_history = monitor.store.entity_status_history["collectors"][collector.name]
    assert status_history["timestamps"] == [0, 1, 2, 3, 4]
    assert status_history["status"][3] == "FAILED"


def test_treatment_that_collects_then_fails_on_one_day_records_failed():
    """The operator's ordering process runs before its failure process and the
    monitor on each tick; a sample taken at intake latched the pre-failure
    status, so availability depended on how often a combo ordered."""
    env = simpy.Environment()
    monitor = WasteMonitor(env)
    treatment = make_treatment(
        env, monitor, initial_waste_storage={PAPER: 0.0},
        order_share_by_waste_type={PAPER: 1.0}, order_up_to_level_m3=100.0,
    )
    treatment.request_waste_directly = lambda volume, _types: DirectRequest({PAPER: volume}, [])

    def collect_then_fail_on_day_two():
        yield env.timeout(2)
        treatment.trigger_collection({PAPER: 10.0})
        treatment.check_failure(env.now, failure_probability=1.0)

    env.process(collect_then_fail_on_day_two())
    env.process(monitor.monitor_system_process([], [], [treatment]))
    env.run(until=4)

    status_history = monitor.store.entity_status_history["treatments"][treatment.name]
    assert status_history["timestamps"] == [0, 1, 2, 3]
    assert status_history["status"][2] == "FAILED"
