"""Treatment status is sampled once per day (T36).

track_processing runs from the daily monitor and from trigger_collection; the
status append sat before the same-timestamp guard, so ordering days counted
twice and availability_treatment_pct leaned toward operational days.
"""

import simpy

from instrumentation.waste_monitor import WasteMonitor
from models.enums import WasteType
from tests.core.factories import make_treatment


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
