"""Costs booked before an entity's first monitor sample are kept (T30).

Treatment runs at t=0 before the monitor process takes its first sample, so
update_entity_costs found no row and dropped the t=0 processing cost (about
EUR 515k, 3.15% of processing cost, Baseline seed 123456).
"""

import simpy
import pytest

from instrumentation.waste_monitor import WasteMonitor
from models.enums import WasteType
from tests.core.factories import make_collector, make_treatment


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def test_treatment_cost_before_first_sample_lands_in_it():
    monitor = WasteMonitor()
    treatment = make_treatment(
        simpy.Environment(), monitor, initial_waste_storage={PAPER: 0.0},
        order_share_by_waste_type={PAPER: 1.0}, order_up_to_level_m3=100.0,
    )

    monitor.update_entity_costs(treatment.name, "treatment", energy_cost=5.0, processing_cost=7.0)
    monitor.track_processing(treatment, timestamp=0)
    monitor.update_entity_costs(treatment.name, "treatment", energy_cost=1.0, processing_cost=2.0)
    monitor.track_processing(treatment, timestamp=1)

    costs = monitor.store.processing_history[treatment.name]["operational"]
    assert costs["energy_costs"] == pytest.approx([6.0, 0.0])
    assert costs["processing_costs"] == pytest.approx([9.0, 0.0])
    assert costs["total_costs"] == pytest.approx([15.0, 0.0])


def test_collector_cost_before_first_sample_lands_in_it():
    monitor = WasteMonitor()
    collector = make_collector(simpy.Environment(), monitor, waste_types=[PAPER])

    monitor.update_entity_costs(collector.name, "collector", transport_cost=4.0)
    monitor.track_collection(collector, timestamp=0)

    history = monitor.store.collection_history[collector.name]
    assert history["transport_costs"] == [4.0]
    assert history["total_costs"] == [4.0]


def test_held_costs_are_kept_apart_for_a_collector_and_treatment_sharing_a_name():
    monitor = WasteMonitor()
    env = simpy.Environment()
    collector = make_collector(env, monitor, waste_types=[PAPER], name="shared")
    treatment = make_treatment(
        env, monitor, name="shared", initial_waste_storage={PAPER: 0.0},
        order_share_by_waste_type={PAPER: 1.0}, order_up_to_level_m3=100.0,
    )

    monitor.update_entity_costs("shared", "collector", transport_cost=4.0)
    monitor.update_entity_costs("shared", "treatment", processing_cost=7.0)
    monitor.track_collection(collector, timestamp=0)
    monitor.track_processing(treatment, timestamp=0)

    assert monitor.store.collection_history["shared"]["transport_costs"] == [4.0]
    assert monitor.store.processing_history["shared"]["operational"]["processing_costs"] == [7.0]
