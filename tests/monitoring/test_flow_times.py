"""Tests for lead/residence-time metrics (Little's Law, C4).

Exercises the pure arithmetic seam (``time_weighted_average``,
``residence_time``) with hand-computed values, then the ``flow_time_metrics``
assembler against a synthetic ``monitor_data`` whose levels, capacities, and
flows are chosen so every stage residence is a round number. Mirrors the
inline-synthetic-dict style of ``test_bullwhip.py`` -- no simulation run.
"""

import pytest

from config.constants import SIMULATION_DURATION
from monitoring.flow_times import (
    flow_time_metrics,
    residence_time,
    time_weighted_average,
)


# --- arithmetic core -------------------------------------------------------

def test_time_weighted_average_of_constant_series_is_that_level():
    avg = time_weighted_average([0.0, 100.0, 365.0], [500.0, 500.0, 500.0], 365.0)
    assert avg == pytest.approx(500.0)


def test_time_weighted_average_of_ramp_is_the_trapezoidal_mean():
    # Linear 0 -> 100 over [0, 10]: average is the midpoint, 50.
    avg = time_weighted_average([0.0, 10.0], [0.0, 100.0], 10.0)
    assert avg == pytest.approx(50.0)


def test_time_weighted_average_holds_last_sample_flat_to_the_horizon():
    # Ramp 0 -> 100 over [0, 10], then flat at 100 over [10, 20]:
    # area = 500 + 1000 = 1500 over horizon 20 -> 75.
    avg = time_weighted_average([0.0, 10.0], [0.0, 100.0], 20.0)
    assert avg == pytest.approx(75.0)


def test_time_weighted_average_single_sample_is_held_across_the_horizon():
    assert time_weighted_average([100.0], [42.0], 365.0) == pytest.approx(42.0)


def test_time_weighted_average_degenerate_inputs_return_none():
    assert time_weighted_average([], [], 365.0) is None
    assert time_weighted_average([0.0], [10.0], 0.0) is None


def test_residence_time_is_wip_over_throughput():
    assert residence_time(500.0, 100.0) == pytest.approx(5.0)


def test_residence_time_undefined_when_throughput_non_positive_or_missing():
    assert residence_time(500.0, 0.0) is None
    assert residence_time(None, 100.0) is None
    assert residence_time(500.0, None) is None


def test_residence_time_satisfies_littles_law_identity():
    wip, throughput = 500.0, 100.0
    res = residence_time(wip, throughput)
    assert throughput * res == pytest.approx(wip)


# --- assembler -------------------------------------------------------------

def _synthetic_monitor_data():
    """A one-node-per-stage run with round-number stage residences.

    Generator: 50% of a 1000 m3 store -> WIP 500; departures 36500 m3 over the
    year -> 100 m3/day -> residence 5 days.
    Collector: 25% of a 2000 m3 store -> WIP 500; collector->treatment 18250 m3
    -> 50 m3/day -> residence 10 days. A collector->collector reposition flow is
    present and must be excluded from collector throughput.
    Treatment: 300 m3 standing -> WIP 300; consumed 36500 m3 -> 100 m3/day ->
    residence 3 days.
    """
    horizon = float(SIMULATION_DURATION)
    return {
        "storage_capacities": {
            "generators": {"gen-A": 1000.0},
            "collectors": {"col-A": 2000.0},
        },
        "generation_history": {
            "gen-A": {
                "timestamps": [0.0, horizon],
                "storage_utilization": [50.0, 50.0],
            },
        },
        "collection_history": {
            "col-A": {
                "timestamps": [0.0, horizon],
                "storage_utilization": [25.0, 25.0],
            },
        },
        "processing_history": {
            "treat-A": {
                "timestamps": [0.0, horizon],
                "storage": {"total": [300.0, 300.0]},
                "processed": {"total": [0.0, 36500.0]},
            },
        },
        "transport_flows": [
            {"source_type": "generator", "target_type": "collector", "volume": 36500.0},
            {"source_type": "collector", "target_type": "treatment", "volume": 18250.0},
            # Cross-region reposition: stays within the collector echelon, so it
            # must NOT count as a collector-stage departure.
            {"source_type": "collector", "target_type": "collector", "volume": 9999.0},
        ],
    }


def test_flow_time_metrics_computes_per_stage_wip_throughput_and_residence():
    metrics = _synthetic_monitor_data()
    result = flow_time_metrics(metrics)

    assert result["generator_wip_m3"] == pytest.approx(500.0)
    assert result["generator_throughput_m3_per_day"] == pytest.approx(100.0)
    assert result["generator_residence_days"] == pytest.approx(5.0)

    assert result["collector_wip_m3"] == pytest.approx(500.0)
    assert result["collector_throughput_m3_per_day"] == pytest.approx(50.0)
    assert result["collector_residence_days"] == pytest.approx(10.0)

    assert result["treatment_wip_m3"] == pytest.approx(300.0)
    assert result["treatment_throughput_m3_per_day"] == pytest.approx(100.0)
    assert result["treatment_residence_days"] == pytest.approx(3.0)

    assert result["total_storage_residence_days"] == pytest.approx(18.0)


def test_flow_time_metrics_on_empty_monitor_data_is_all_none():
    result = flow_time_metrics({})
    assert set(result) == {
        "generator_wip_m3",
        "generator_throughput_m3_per_day",
        "generator_residence_days",
        "collector_wip_m3",
        "collector_throughput_m3_per_day",
        "collector_residence_days",
        "treatment_wip_m3",
        "treatment_throughput_m3_per_day",
        "treatment_residence_days",
        "total_storage_residence_days",
    }
    assert all(value is None for value in result.values())


def test_missing_capacities_leave_utilization_stages_none_but_treatment_computed():
    # Without storage_capacities the generator/collector absolute inventory
    # cannot be recovered, so those stages are None; treatment (absolute m3) is
    # unaffected. total folds in only the present (treatment) residence.
    data = _synthetic_monitor_data()
    del data["storage_capacities"]

    result = flow_time_metrics(data)

    assert result["generator_wip_m3"] is None
    assert result["generator_residence_days"] is None
    assert result["collector_wip_m3"] is None
    assert result["collector_residence_days"] is None
    assert result["treatment_residence_days"] == pytest.approx(3.0)
    assert result["total_storage_residence_days"] == pytest.approx(3.0)
