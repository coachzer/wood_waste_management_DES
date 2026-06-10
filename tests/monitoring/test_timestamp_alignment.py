"""Tests for timestamp-aligned aggregation in the visualization layer (VIZ-REVIEW T4).

Failure mode guarded: the per-timestamp aggregators keyed ``{float timestamp: sum}``
and implicitly assumed every entity logged at exactly the same times. For
cumulative series (``total_generated``, ``collected_volumes``), at any timestamp
an entity did not log, its already-accumulated volume dropped out of the sum and
the aggregate curve sawed downward. The fix aligns on the union of timestamps
with per-series-class gap semantics: cumulative (forward-fill, zero before first
observation), level (forward-fill, backfill first value), rate (forward-fill
then average, excluded before first observation).

Non-vacuity: the misaligned fixtures below make the pre-fix dict-sum
implementation red (saw-tooth values asserted against).
"""

import pytest

from visualization.visualization_utils import (
    aggregate_collection_data,
    aggregate_generation_data,
    calculate_average_efficiency,
    calculate_storage_levels,
)


def _generator_history(timestamps, totals_by_type):
    return {
        "timestamps": list(timestamps),
        "total_generated": {
            waste_type: list(values) for waste_type, values in totals_by_type.items()
        },
    }


def test_misaligned_cumulative_series_forward_fills_instead_of_sawing():
    # gen_b misses t=1 and t=3; its accumulated volume must persist, not drop out.
    history = {
        "gen_a": _generator_history([0.0, 1.0, 2.0, 3.0], {"wood": [10.0, 20.0, 30.0, 40.0]}),
        "gen_b": _generator_history([0.0, 2.0], {"wood": [5.0, 15.0]}),
    }

    result = aggregate_generation_data(history)

    assert result["timestamps"] == [0.0, 1.0, 2.0, 3.0]
    assert result["volumes"] == [15.0, 25.0, 45.0, 55.0]


def test_shared_cadence_input_aggregates_as_plain_per_timestamp_sum():
    # The monitor loop samples every entity each tick; on aligned input the
    # alignment must be a no-op relative to the pre-fix per-timestamp sum.
    history = {
        "gen_a": _generator_history(
            [0.0, 1.0, 2.0],
            {"wood": [10.0, 20.0, 30.0], "bark": [1.0, 2.0, 3.0]},
        ),
        "gen_b": _generator_history([0.0, 1.0, 2.0], {"wood": [5.0, 10.0, 15.0]}),
    }

    result = aggregate_generation_data(history)

    assert result["timestamps"] == [0.0, 1.0, 2.0]
    assert result["volumes"] == [16.0, 32.0, 48.0]


def test_misaligned_cumulative_collection_volumes_forward_fill():
    # collected_volumes tracks collector.collected_waste, a running total.
    history = {
        "col_a": {
            "timestamps": [0.0, 1.0, 2.0],
            "collected_volumes": {"wood": [4.0, 8.0, 12.0]},
        },
        "col_b": {
            "timestamps": [1.0],
            "collected_volumes": {"wood": [6.0]},
        },
    }

    result = aggregate_collection_data(history)

    assert result["timestamps"] == [0.0, 1.0, 2.0]
    # col_b contributes zero before its first observation, then persists.
    assert result["volumes"] == [4.0, 14.0, 18.0]


def test_misaligned_storage_levels_backfill_first_observation():
    # storage.total is a sampled stock level: a buffer primed before the
    # monitor's first sample existed before t — extend the first value
    # backward instead of plotting a phantom dip.
    history = {
        "proc_a": {
            "timestamps": [0.0, 1.0, 2.0],
            "storage": {"total": [100.0, 110.0, 120.0]},
        },
        "proc_b": {
            "timestamps": [1.0, 2.0],
            "storage": {"total": [50.0, 60.0]},
        },
    }

    result = calculate_storage_levels(history)

    assert result["timestamps"] == [0.0, 1.0, 2.0]
    assert result["storage"] == [150.0, 160.0, 180.0]


def test_misaligned_efficiency_forward_fills_then_averages():
    # Efficiency is a sampled state variable. At an off-cadence timestamp the
    # other entities' last-known values persist into the mean — one entity's
    # lone sample must not collapse the average to its own value. Before an
    # entity's first observation it is excluded from the mean.
    history = {
        "ent_a": {"timestamps": [0.0, 1.0, 2.0], "efficiency": [80.0, 90.0, 100.0]},
        "ent_b": {"timestamps": [1.5], "efficiency": [40.0]},
    }

    result = calculate_average_efficiency(history)

    assert result["timestamps"] == [0.0, 1.0, 1.5, 2.0]
    assert result["efficiency"] == [80.0, 90.0, 65.0, 70.0]


def test_series_length_mismatch_raises_instead_of_silently_skipping():
    # The pre-fix guard silently dropped a whole waste type whose series
    # length differed from the timestamp vector; corrupted monitor history
    # must crash the plot run, not misplot a smaller total.
    history = {
        "gen_a": _generator_history([0.0, 1.0, 2.0], {"wood": [10.0, 20.0]}),
    }

    with pytest.raises(ValueError, match="gen_a"):
        aggregate_generation_data(history)


def test_non_monotonic_timestamps_raise():
    history = {
        "ent_a": {"timestamps": [0.0, 2.0, 1.0], "efficiency": [80.0, 90.0, 100.0]},
    }

    with pytest.raises(ValueError, match="ent_a"):
        calculate_average_efficiency(history)
