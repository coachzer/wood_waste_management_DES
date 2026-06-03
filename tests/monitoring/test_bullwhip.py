"""Tests for the throughput-bullwhip metric (ADR 0004).

Three layers are exercised: the arithmetic core (``cv_squared``,
``bullwhip_ratio``) against hand-computed values and degenerate guards; the
Treatment-echelon aggregation, including the load-bearing choice to anchor on
consumption ``attempted`` rather than ``consumed``; and the wiring that surfaces
``bullwhip.treatment_anchored`` in the per-run KPI dict produced by
``extract_kpis``.
"""

import math

from config.constants import (
    BULLWHIP_BIN_WIDTH_DAYS,
    BULLWHIP_WARMUP_WEEKS,
    WEEKS_PER_YEAR,
)
from monitoring.baseline_aggregate import extract_kpis
from monitoring.bullwhip import (
    bullwhip_ratio,
    collector_anchored_bullwhip,
    cv_squared,
    treatment_anchored_bullwhip,
)


# --- arithmetic core --------------------------------------------------------


def test_cv_squared_matches_hand_computed_value():
    # series [2, 4, 6, 8]: mean 5, population variance (9+1+1+9)/4 = 5,
    # CV^2 = 5 / 5^2 = 0.2.
    assert cv_squared([2.0, 4.0, 6.0, 8.0]) == 0.2


def test_cv_squared_constant_nonzero_series_is_zero():
    # No dispersion but a defined mean -> CV^2 is 0.0 (not None).
    assert cv_squared([5.0, 5.0, 5.0, 5.0]) == 0.0


def test_cv_squared_zero_mean_is_none():
    # Mean is zero -> the mean-square normalization is undefined.
    assert cv_squared([0.0, 0.0, 0.0]) is None
    assert cv_squared([-3.0, 3.0]) is None


def test_cv_squared_fewer_than_two_bins_is_none():
    assert cv_squared([7.0]) is None
    assert cv_squared([]) is None


def test_bullwhip_ratio_pass_through_is_one():
    # Identical flow and consumption series -> clean pass-through, ratio 1.0.
    series = [1.0, 3.0, 2.0, 4.0]
    assert bullwhip_ratio(series, list(series)) == 1.0


def test_bullwhip_ratio_amplified_is_greater_than_one():
    # Flow far lumpier than a near-flat consumption anchor -> amplification.
    consumption = [10.0, 10.0, 10.0, 12.0]
    flow = [0.0, 40.0, 0.0, 40.0]
    ratio = bullwhip_ratio(flow, consumption)
    assert ratio is not None and ratio > 1.0


def test_bullwhip_ratio_flat_anchor_is_none():
    # Constant consumption -> CV^2(consumption) == 0 -> ratio undefined.
    assert bullwhip_ratio([1.0, 2.0, 3.0, 4.0], [5.0, 5.0, 5.0, 5.0]) is None


def test_bullwhip_ratio_undefined_numerator_is_none():
    # Zero-mean flow -> CV^2(flow) is None -> ratio undefined.
    assert bullwhip_ratio([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) is None


# --- Treatment-echelon aggregation ------------------------------------------


def _analysis_week_timestamp(week_index):
    """Timestamp (days) landing squarely inside 0-based ``week_index``."""
    return week_index * BULLWHIP_BIN_WIDTH_DAYS + 1.0


def _make_consumption_event(week_index, attempted, consumed):
    return {
        "timestamp": _analysis_week_timestamp(week_index),
        "operator": "treatment-1",
        "product": "mdf",
        "attempted": attempted,
        "consumed": consumed,
        "lost": max(0.0, attempted - consumed),
        "reason": None,
    }


def _make_inbound_flow(week_index, volume, target_name="treatment-1"):
    return {
        "source_type": "collector",
        "source_name": "collector-1",
        "target_type": "treatment",
        "target_name": target_name,
        "waste_type": "17 02 01",
        "volume": volume,
        "timestamp": _analysis_week_timestamp(week_index),
        "transport_method": "inter_region_transport",
    }


def _analysis_weeks():
    return range(BULLWHIP_WARMUP_WEEKS, WEEKS_PER_YEAR - 1 + 1)


def test_denominator_uses_attempted_not_consumed():
    """The consumption anchor is ``attempted``; ``consumed`` is held flat so the
    two choices give provably different results.

    Attempted alternates (dispersion present); consumed is constant (dispersion
    zero). Anchoring on ``consumed`` would make CV^2(anchor) == 0 and the metric
    undefined; anchoring on ``attempted`` yields the single node's defined
    ratio. So a finite result here can only come from using ``attempted``.
    """
    consumption_events = []
    transport_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 200.0
        consumption_events.append(_make_consumption_event(week_index, attempted, 50.0))
        volume = 30.0 if offset % 2 == 0 else 90.0
        transport_flows.append(_make_inbound_flow(week_index, volume))

    result = treatment_anchored_bullwhip(transport_flows, consumption_events)

    # Single node -> the volume-weighted mean is just that node's ratio against
    # the attempted anchor. Recompute it directly to pin the value.
    attempted_bins = [
        100.0 if offset % 2 == 0 else 200.0 for offset in range(len(consumption_events))
    ]
    volume_bins = [
        30.0 if offset % 2 == 0 else 90.0 for offset in range(len(transport_flows))
    ]
    expected = bullwhip_ratio(volume_bins, attempted_bins)
    assert result is not None
    assert math.isclose(result, expected, rel_tol=1e-12)

    # The same series anchored on the (flat) consumed values would be undefined.
    consumed_bins = [50.0] * len(consumption_events)
    assert bullwhip_ratio(volume_bins, consumed_bins) is None


def test_warmup_weeks_are_excluded():
    """Flows and consumption inside the first BULLWHIP_WARMUP_WEEKS weeks must
    not affect the result -- only weeks 5-52 are measured."""
    base_events = []
    base_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 200.0
        base_events.append(_make_consumption_event(week_index, attempted, attempted))
        volume = 30.0 if offset % 2 == 0 else 90.0
        base_flows.append(_make_inbound_flow(week_index, volume))

    without_warmup = treatment_anchored_bullwhip(base_flows, base_events)

    # Inject wild spikes into the warm-up weeks (indices 0 .. WARMUP-1).
    warmup_events = list(base_events)
    warmup_flows = list(base_flows)
    for week_index in range(BULLWHIP_WARMUP_WEEKS):
        warmup_events.append(_make_consumption_event(week_index, 9999.0, 9999.0))
        warmup_flows.append(_make_inbound_flow(week_index, 9999.0))

    with_warmup = treatment_anchored_bullwhip(warmup_flows, warmup_events)
    assert without_warmup is not None
    assert math.isclose(without_warmup, with_warmup, rel_tol=1e-12)


def test_volume_weighting_down_weights_tiny_node():
    """A high-volume steady node and a tiny lumpy node: the volume-weighted mean
    must sit near the dominant node's ratio, not be dragged up by the tiny
    node's inflated CV^2."""
    consumption_events = []
    big_node_flows = []
    tiny_node_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 200.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        # Big node tracks consumption closely (low amplification).
        big_volume = 1000.0 if offset % 2 == 0 else 2000.0
        big_node_flows.append(_make_inbound_flow(week_index, big_volume, "treatment-big"))
        # Tiny node spikes on and off (huge CV^2) but carries negligible volume.
        tiny_volume = 0.0 if offset % 2 == 0 else 5.0
        tiny_node_flows.append(_make_inbound_flow(week_index, tiny_volume, "treatment-tiny"))

    big_only = treatment_anchored_bullwhip(big_node_flows, consumption_events)
    combined = treatment_anchored_bullwhip(
        big_node_flows + tiny_node_flows, consumption_events
    )
    assert big_only is not None and combined is not None
    # The tiny node's extreme ratio barely moves the weighted mean.
    assert abs(combined - big_only) < 0.05 * big_only


def test_no_inbound_flow_yields_none():
    consumption_events = [
        _make_consumption_event(week_index, 100.0, 100.0)
        for week_index in _analysis_weeks()
    ]
    assert treatment_anchored_bullwhip([], consumption_events) is None


# --- Collector-echelon aggregation ------------------------------------------


def _make_generator_flow(week_index, volume, target_name="collector-1"):
    return {
        "source_type": "generator",
        "source_name": "generator-1",
        "target_type": "collector",
        "target_name": target_name,
        "waste_type": "17 02 01",
        "volume": volume,
        "timestamp": _analysis_week_timestamp(week_index),
        "transport_method": "collection_vehicle",
    }


def test_collector_uses_generator_to_collector_link_not_treatment():
    """The collector echelon reads ``generator->collector`` flow. Feeding it only
    ``collector->treatment`` flow (the Treatment echelon's link) yields None --
    proving the two echelons key off distinct links, not the same records."""
    consumption_events = []
    treatment_only_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 200.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        volume = 30.0 if offset % 2 == 0 else 90.0
        treatment_only_flows.append(_make_inbound_flow(week_index, volume))

    assert collector_anchored_bullwhip(treatment_only_flows, consumption_events) is None
    # The same flows DO define the Treatment echelon -- so the input is valid,
    # only the link differs.
    assert treatment_anchored_bullwhip(treatment_only_flows, consumption_events) is not None


def test_collector_echelon_shares_the_core_amplified_case():
    """An amplified generator->collector series flows through the shared core to
    a defined ratio > 1, matching a direct ``bullwhip_ratio`` recompute."""
    consumption_events = []
    generator_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 200.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        volume = 10.0 if offset % 2 == 0 else 200.0
        generator_flows.append(_make_generator_flow(week_index, volume))

    result = collector_anchored_bullwhip(generator_flows, consumption_events)

    attempted_bins = [
        100.0 if offset % 2 == 0 else 200.0 for offset in range(len(consumption_events))
    ]
    volume_bins = [
        10.0 if offset % 2 == 0 else 200.0 for offset in range(len(generator_flows))
    ]
    expected = bullwhip_ratio(volume_bins, attempted_bins)
    assert result is not None and result > 1.0
    assert math.isclose(result, expected, rel_tol=1e-12)


# --- KPI wiring -------------------------------------------------------------


def _amplified_run_logs():
    """Synthetic single-run logs with defined, amplified bullwhip at both
    echelons -- collector->treatment and generator->collector flow alongside the
    consumption anchor."""
    consumption_events = []
    transport_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        treatment_volume = 10.0 if offset % 2 == 0 else 200.0
        transport_flows.append(_make_inbound_flow(week_index, treatment_volume))
        collector_volume = 15.0 if offset % 2 == 0 else 180.0
        transport_flows.append(_make_generator_flow(week_index, collector_volume))
    return transport_flows, consumption_events


def test_extract_kpis_emits_bullwhip_namespace():
    transport_flows, consumption_events = _amplified_run_logs()
    monitor_data = {
        "transport_flows": transport_flows,
        "consumption_events": consumption_events,
    }

    kpis = extract_kpis(monitor_data)

    assert "bullwhip" in kpis
    for echelon in ("treatment_anchored", "collector_anchored"):
        value = kpis["bullwhip"][echelon]
        assert value is not None
        assert math.isfinite(value)
        assert value > 0.0


def test_extract_kpis_bullwhip_is_none_without_logs():
    # Missing logs (e.g. a monitor_data without the raw flows) -> None, no crash.
    kpis = extract_kpis({})
    assert kpis["bullwhip"]["treatment_anchored"] is None
    assert kpis["bullwhip"]["collector_anchored"] is None
