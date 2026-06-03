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
    collector_anchored_pooled_bullwhip,
    cv_squared,
    generation_floor_cv2,
    stage_bullwhip,
    treatment_anchored_bullwhip,
    treatment_anchored_pooled_bullwhip,
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


def _make_reposition_flow(week_index, volume, target_name="collector-2"):
    """A cross-region repositioning move: collector -> collector (ADR 0009)."""
    flow = _make_inbound_flow(week_index, volume, target_name=target_name)
    flow["target_type"] = "collector"
    return flow


def test_treatment_echelon_reads_intake_not_repositioning():
    """The Treatment echelon reads the collector->treatment intake link only; the
    collector->collector repositioning move is invisible to it (ADR 0009).

    Pinned by contrast: counting the lumpy reposition would move the metric, so
    if it were still mislabeled onto the treatment link (the pre-ADR-0009 bug)
    the result would differ from the intake-only value.
    """
    consumption_events = []
    intake_flows = []
    reposition_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        consumption_events.append(
            _make_consumption_event(week_index, 100.0 if offset % 2 == 0 else 200.0, 50.0)
        )
        intake_flows.append(_make_inbound_flow(week_index, 30.0 if offset % 2 == 0 else 90.0))
        # Lumpy reposition that would dominate the echelon if it were counted.
        reposition_flows.append(
            _make_reposition_flow(week_index, 0.0 if offset % 2 == 0 else 800.0)
        )

    intake_only = treatment_anchored_bullwhip(intake_flows, consumption_events)
    with_reposition = treatment_anchored_bullwhip(
        intake_flows + reposition_flows, consumption_events
    )

    assert intake_only is not None
    # collector->collector is filtered out of the Treatment echelon entirely.
    assert with_reposition == intake_only

    # Mislabel the same reposition onto collector->treatment (the old bug): it
    # now enters the echelon as a second node and shifts the metric.
    mislabeled = []
    for flow in reposition_flows:
        polluting = dict(flow)
        polluting["target_type"] = "treatment"
        mislabeled.append(polluting)
    polluted = treatment_anchored_bullwhip(intake_flows + mislabeled, consumption_events)
    assert polluted != intake_only


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


# --- Stage-by-stage diagnostic ----------------------------------------------


def test_stage_ratios_telescope_to_pooled_anchored():
    """The two stage ratios must telescope exactly to the pooled collector
    anchored ratio (ADR 0006): treatment_stage * collector_stage ==
    CV^2(pooled collector inbound) / CV^2(consumption).

    Two out-of-phase nodes per echelon, so pooling genuinely differs from any
    single node -- if the implementation grouped by node the pooled identity
    would not recompute cleanly here."""
    consumption_events = []
    transport_flows = []
    pooled_treatment = []
    pooled_collector = []
    attempted_bins = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        attempted_bins.append(attempted)

        # Two treatment nodes, out of phase -> pooled series is neither node's.
        t_a = 10.0 if offset % 2 == 0 else 200.0
        t_b = 50.0 if offset % 2 == 0 else 80.0
        transport_flows.append(_make_inbound_flow(week_index, t_a, "treatment-a"))
        transport_flows.append(_make_inbound_flow(week_index, t_b, "treatment-b"))
        pooled_treatment.append(t_a + t_b)

        # Two collector nodes, also out of phase.
        c_a = 15.0 if offset % 2 == 0 else 180.0
        c_b = 40.0 if offset % 2 == 0 else 60.0
        transport_flows.append(_make_generator_flow(week_index, c_a, "collector-a"))
        transport_flows.append(_make_generator_flow(week_index, c_b, "collector-b"))
        pooled_collector.append(c_a + c_b)

    treatment_stage, collector_stage = stage_bullwhip(transport_flows, consumption_events)

    assert treatment_stage is not None and collector_stage is not None
    # Each stage matches its pooled definition exactly.
    assert math.isclose(
        treatment_stage,
        bullwhip_ratio(pooled_treatment, attempted_bins),
        rel_tol=1e-12,
    )
    assert math.isclose(
        collector_stage,
        bullwhip_ratio(pooled_collector, pooled_treatment),
        rel_tol=1e-12,
    )
    # The telescoping identity: the product is the pooled collector anchored ratio.
    expected_pooled_anchored = bullwhip_ratio(pooled_collector, attempted_bins)
    assert math.isclose(
        treatment_stage * collector_stage, expected_pooled_anchored, rel_tol=1e-9
    )


def test_treatment_stage_is_pooled_not_per_node_headline():
    """treatment_stage is the pooled ratio, NOT the per-node-weighted
    treatment_anchored headline (ADR 0006). With out-of-phase nodes, pooling
    smooths the spikes, so the pooled stage sits below the per-node headline --
    the two are provably different numbers, not the same value reported twice."""
    consumption_events = []
    transport_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        # Two strongly out-of-phase treatment nodes: each lumpy, pooled near-flat.
        t_a = 10.0 if offset % 2 == 0 else 200.0
        t_b = 180.0 if offset % 2 == 0 else 20.0
        transport_flows.append(_make_inbound_flow(week_index, t_a, "treatment-a"))
        transport_flows.append(_make_inbound_flow(week_index, t_b, "treatment-b"))

    treatment_stage, _ = stage_bullwhip(transport_flows, consumption_events)
    per_node_headline = treatment_anchored_bullwhip(transport_flows, consumption_events)

    assert treatment_stage is not None and per_node_headline is not None
    # Pooling understates the per-node amplification -> strictly smaller, and not
    # merely a floating-point hair apart.
    assert treatment_stage < per_node_headline
    assert not math.isclose(treatment_stage, per_node_headline, rel_tol=1e-3)


def test_stage_bullwhip_none_without_flows():
    """No flow at all -> both stages undefined, no crash."""
    consumption_events = [
        _make_consumption_event(week_index, 100.0, 100.0)
        for week_index in _analysis_weeks()
    ]
    assert stage_bullwhip([], consumption_events) == (None, None)


# --- Pooled anchored robustness variant -------------------------------------


def test_treatment_pooled_equals_treatment_stage():
    """The pooled Treatment anchored variant coincides exactly with the
    diagnostic ``treatment_stage`` (ADR 0007): both are CV^2(pooled
    collector->treatment inbound) / CV^2(consumption). Two out-of-phase nodes so
    the pooled series is neither node's -- a per-node implementation would not
    reproduce the stage value here."""
    consumption_events = []
    transport_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        t_a = 10.0 if offset % 2 == 0 else 200.0
        t_b = 50.0 if offset % 2 == 0 else 80.0
        transport_flows.append(_make_inbound_flow(week_index, t_a, "treatment-a"))
        transport_flows.append(_make_inbound_flow(week_index, t_b, "treatment-b"))

    pooled = treatment_anchored_pooled_bullwhip(transport_flows, consumption_events)
    treatment_stage, _ = stage_bullwhip(transport_flows, consumption_events)

    assert pooled is not None and treatment_stage is not None
    assert math.isclose(pooled, treatment_stage, rel_tol=1e-12)


def test_collector_pooled_equals_telescoped_stage_product():
    """The pooled Collector anchored variant matches no single stage; it equals
    the telescoped product treatment_stage * collector_stage (ADR 0007), and a
    direct pooled recompute against the consumption anchor."""
    consumption_events = []
    transport_flows = []
    pooled_collector = []
    attempted_bins = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        attempted_bins.append(attempted)
        # Treatment flow so the stage product is defined.
        transport_flows.append(_make_inbound_flow(week_index, 30.0 if offset % 2 == 0 else 90.0))
        c_a = 15.0 if offset % 2 == 0 else 180.0
        c_b = 40.0 if offset % 2 == 0 else 60.0
        transport_flows.append(_make_generator_flow(week_index, c_a, "collector-a"))
        transport_flows.append(_make_generator_flow(week_index, c_b, "collector-b"))
        pooled_collector.append(c_a + c_b)

    pooled = collector_anchored_pooled_bullwhip(transport_flows, consumption_events)
    treatment_stage, collector_stage = stage_bullwhip(transport_flows, consumption_events)

    assert pooled is not None
    # Direct pooled recompute: CV^2(pooled generator->collector) / CV^2(attempted).
    assert math.isclose(
        pooled, bullwhip_ratio(pooled_collector, attempted_bins), rel_tol=1e-12
    )
    # And the telescoped stage product.
    assert treatment_stage is not None and collector_stage is not None
    assert math.isclose(pooled, treatment_stage * collector_stage, rel_tol=1e-9)


def test_pooled_understates_per_node_headline():
    """The pooled variant is the conservative lower bound: with out-of-phase
    nodes it sits strictly below the per-node volume-weighted headline (ADR 0004),
    proving the two are distinct aggregations, not the same value twice."""
    consumption_events = []
    transport_flows = []
    for offset, week_index in enumerate(_analysis_weeks()):
        attempted = 100.0 if offset % 2 == 0 else 120.0
        consumption_events.append(_make_consumption_event(week_index, attempted, attempted))
        # Two strongly out-of-phase collectors: each lumpy, pooled near-flat.
        c_a = 10.0 if offset % 2 == 0 else 200.0
        c_b = 180.0 if offset % 2 == 0 else 20.0
        transport_flows.append(_make_generator_flow(week_index, c_a, "collector-a"))
        transport_flows.append(_make_generator_flow(week_index, c_b, "collector-b"))

    pooled = collector_anchored_pooled_bullwhip(transport_flows, consumption_events)
    per_node_headline = collector_anchored_bullwhip(transport_flows, consumption_events)

    assert pooled is not None and per_node_headline is not None
    assert pooled < per_node_headline
    assert not math.isclose(pooled, per_node_headline, rel_tol=1e-3)


def test_pooled_anchored_none_without_flows():
    """No flow at all -> both pooled variants undefined, no crash."""
    consumption_events = [
        _make_consumption_event(week_index, 100.0, 100.0)
        for week_index in _analysis_weeks()
    ]
    assert treatment_anchored_pooled_bullwhip([], consumption_events) is None
    assert collector_anchored_pooled_bullwhip([], consumption_events) is None


# --- Generation source-variance floor ---------------------------------------


def _make_generation_node(weekly_increments_by_type, weeks=None):
    """Build a ``WasteMonitor.generation_history`` node from weekly increments.

    ``weekly_increments_by_type``: ``{waste_type: [per-week potential volume]}``,
    aligned to ``weeks`` (defaulting to the analysis weeks).
    ``total_potential_generated`` is stored as the running cumulative sum (as the
    monitor records it), one tracking step per week timestamped inside that week
    -- so differencing the cumulative recovers the per-week increment exactly.
    """
    weeks = list(weeks) if weeks is not None else list(_analysis_weeks())
    timestamps = [_analysis_week_timestamp(week_index) for week_index in weeks]
    total_potential_generated = {}
    for waste_type, increments in weekly_increments_by_type.items():
        cumulative_series = []
        running_total = 0.0
        for increment in increments:
            running_total += increment
            cumulative_series.append(running_total)
        total_potential_generated[waste_type] = cumulative_series
    return {
        "timestamps": timestamps,
        "total_potential_generated": total_potential_generated,
    }


def test_generation_floor_is_raw_cv_squared_of_weekly_generation():
    """Single node, single waste type: the floor is the raw CV^2 of the weekly
    generated volume -- a reference value, NOT a ratio against consumption (the
    function takes no consumption series)."""
    week_count = len(list(_analysis_weeks()))
    increments = [100.0 if i % 2 == 0 else 200.0 for i in range(week_count)]
    node = _make_generation_node({"17 02 01": increments})

    result = generation_floor_cv2({"generator-1": node})

    assert result is not None
    assert math.isclose(result, cv_squared(increments), rel_tol=1e-12)


def test_generation_floor_sums_waste_types_per_step():
    """A node's weekly volume is the sum across its waste types before CV^2."""
    week_count = len(list(_analysis_weeks()))
    type_a = [100.0 if i % 2 == 0 else 200.0 for i in range(week_count)]
    type_b = [10.0] * week_count
    node = _make_generation_node({"17 02 01": type_a, "03 01 05": type_b})

    result = generation_floor_cv2({"generator-1": node})

    combined = [a + b for a, b in zip(type_a, type_b)]
    assert math.isclose(result, cv_squared(combined), rel_tol=1e-12)


def test_generation_floor_excludes_warmup_weeks():
    """Wild generation inside the first BULLWHIP_WARMUP_WEEKS weeks must not move
    the floor -- only weeks 5-52 are measured."""
    analysis_weeks = list(_analysis_weeks())
    increments = [100.0 if i % 2 == 0 else 200.0 for i in range(len(analysis_weeks))]
    baseline = generation_floor_cv2(
        {"generator-1": _make_generation_node({"17 02 01": increments})}
    )

    warmup_weeks = list(range(BULLWHIP_WARMUP_WEEKS))
    all_weeks = warmup_weeks + analysis_weeks
    spiked = [9999.0] * len(warmup_weeks) + increments
    with_warmup = generation_floor_cv2(
        {"generator-1": _make_generation_node({"17 02 01": spiked}, weeks=all_weeks)}
    )

    assert baseline is not None
    assert math.isclose(baseline, with_warmup, rel_tol=1e-12)


def test_generation_floor_volume_weights_nodes():
    """Volume-weighting must collapse a tiny-volume node's influence to a small
    fraction of what an unweighted (equal-weight) average would give -- for ANY
    dominant node, not just one whose CV^2 happens to swamp the perturbation.

    The dominant node is deliberately *steady* (low CV^2), the worst case for a
    relative-tolerance check: the test instead measures the tiny node's pull
    against the equal-weighted alternative, isolating the weighting mechanism."""
    week_count = len(list(_analysis_weeks()))
    big = [1000.0 if i % 2 == 0 else 1100.0 for i in range(week_count)]
    tiny = [0.0 if i % 2 == 0 else 5.0 for i in range(week_count)]
    big_node = _make_generation_node({"17 02 01": big})
    tiny_node = _make_generation_node({"17 02 01": tiny})

    big_only = generation_floor_cv2({"generator-big": big_node})
    combined = generation_floor_cv2(
        {"generator-big": big_node, "generator-tiny": tiny_node}
    )
    # The unweighted mean of the two node CV^2 values -- what we'd get if the
    # tiny node carried equal weight despite its negligible volume.
    equal_weighted = (cv_squared(big) + cv_squared(tiny)) / 2.0

    assert big_only is not None and combined is not None
    # Volume-weighting pulls the tiny node's contribution to under 1% of its
    # equal-weight pull, so `combined` stays near `big_only` no matter how small
    # `big_only` is.
    assert abs(combined - big_only) < 0.01 * abs(equal_weighted - big_only)


def test_generation_floor_empty_history_is_none():
    assert generation_floor_cv2({}) is None


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
    week_count = len(list(_analysis_weeks()))
    generation = {
        "generator-1": _make_generation_node(
            {"17 02 01": [100.0 if i % 2 == 0 else 200.0 for i in range(week_count)]}
        )
    }
    monitor_data = {
        "transport_flows": transport_flows,
        "consumption_events": consumption_events,
        "generation_history": generation,
    }

    kpis = extract_kpis(monitor_data)

    assert "bullwhip" in kpis
    for key in (
        "treatment_anchored",
        "collector_anchored",
        "treatment_stage",
        "collector_stage",
        "treatment_anchored_pooled",
        "collector_anchored_pooled",
    ):
        value = kpis["bullwhip"][key]
        assert value is not None
        assert math.isfinite(value)
        assert value > 0.0
    # The pooled Treatment variant coincides with treatment_stage by construction.
    assert math.isclose(
        kpis["bullwhip"]["treatment_anchored_pooled"],
        kpis["bullwhip"]["treatment_stage"],
        rel_tol=1e-12,
    )
    floor = kpis["bullwhip"]["generation_floor_cv2"]
    assert floor is not None and math.isfinite(floor) and floor >= 0.0


def test_extract_kpis_bullwhip_is_none_without_logs():
    # Missing logs (e.g. a monitor_data without the raw flows) -> None, no crash.
    kpis = extract_kpis({})
    assert kpis["bullwhip"]["treatment_anchored"] is None
    assert kpis["bullwhip"]["collector_anchored"] is None
    assert kpis["bullwhip"]["treatment_stage"] is None
    assert kpis["bullwhip"]["collector_stage"] is None
    assert kpis["bullwhip"]["treatment_anchored_pooled"] is None
    assert kpis["bullwhip"]["collector_anchored_pooled"] is None
    assert kpis["bullwhip"]["generation_floor_cv2"] is None
