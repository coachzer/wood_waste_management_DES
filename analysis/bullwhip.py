"""Throughput-bullwhip measurement (ADR 0004): a post-hoc CV^2-normalized
flow-amplification ratio read from a single run's persisted ``transport_flows``
and ``consumption_events`` logs. It does not touch the simulation, so adding it
keeps the golden byte-identical exit test valid.

Layering keeps the arithmetic core a sim/IO-free unit-test seam:
``cv_squared`` / ``bullwhip_ratio`` take plain numeric sequences;
``_echelon_anchored_bullwhip`` adds weekly binning and per-node volume-weighted
aggregation; ``treatment_anchored_bullwhip`` (collector->treatment) and
``collector_anchored_bullwhip`` (generator->collector) are thin link-picking
wrappers anchored on the same consumption series. ``stage_bullwhip`` is the
pooled decomposition (ADR 0006), ``pooled_anchored_bullwhip`` the pooled
robustness variant (ADR 0007), and ``generation_floor_cv2`` the policy-invariant
source-variance reference (ADR 0005). See those ADRs for the rationale behind
each choice; the **Throughput Bullwhip** glossary term in CONTEXT.md defines the
measure.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from config.constants import (
    BULLWHIP_BIN_WIDTH_DAYS,
    BULLWHIP_WARMUP_WEEKS,
    WEEKS_PER_YEAR,
)


def cv_squared(series: Sequence[float]) -> Optional[float]:
    """Squared coefficient of variation: ``var / mean**2`` (population variance).

    The unit-free dispersion measure underlying the throughput-bullwhip ratio
    (ADR 0004). Returns ``None`` where it is undefined -- fewer than two bins or a
    zero mean (the normalization explodes).
    """
    bin_count = len(series)
    if bin_count < 2:
        return None
    mean = sum(series) / bin_count
    if mean == 0:
        return None
    variance = sum((value - mean) ** 2 for value in series) / bin_count
    return variance / (mean ** 2)


def bullwhip_ratio(
    flow_series: Sequence[float], consumption_series: Sequence[float]
) -> Optional[float]:
    """Throughput bullwhip = ``CV^2(flow) / CV^2(consumption)`` (ADR 0004).

    ``> 1`` is amplification, ``1`` is clean pass-through. Returns ``None`` when
    either CV^2 is undefined, or the consumption CV^2 is zero (a flat anchor
    leaves nothing to normalize against).
    """
    flow_cv_squared = cv_squared(flow_series)
    consumption_cv_squared = cv_squared(consumption_series)
    if (
        flow_cv_squared is None
        or consumption_cv_squared is None
        or consumption_cv_squared == 0
    ):
        return None
    return flow_cv_squared / consumption_cv_squared


def _weekly_bins(records: Sequence[Dict[str, Any]], value_key: str) -> List[float]:
    """Sum ``value_key`` of each record into post-warm-up weekly bins.

    Records are bucketed by ``timestamp`` (days) into BULLWHIP_BIN_WIDTH_DAYS
    bins over 0-based week indices BULLWHIP_WARMUP_WEEKS .. WEEKS_PER_YEAR - 1
    (weeks 5-52, dropping the 4-week cold-start ramp; ADR 0004). Every week in the
    window gets a bin -- empty weeks stay 0.0. Records outside the window
    (warm-up, or the trailing partial week) are ignored.
    """
    start_week = BULLWHIP_WARMUP_WEEKS
    end_week = WEEKS_PER_YEAR - 1
    bins = [0.0] * (end_week - start_week + 1)
    for record in records:
        timestamp = record.get("timestamp")
        if timestamp is None:
            continue
        week_index = int(timestamp / BULLWHIP_BIN_WIDTH_DAYS)
        if start_week <= week_index <= end_week:
            bins[week_index - start_week] += record.get(value_key, 0.0)
    return bins


def _generation_increment_records(
    node_history: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Per-step generated-volume records for one generator node.

    Differences each waste type's cumulative ``total_potential_generated`` series
    (stored parallel to ``timestamps``) into per-step increments and sums across
    waste types. Uses *potential* generation, not committed ``total_generated``,
    so the floor stays policy-invariant (ADR 0005). Each waste type is differenced
    independently so a series shorter than ``timestamps`` cannot inject a spurious
    negative increment. Returns ``{"timestamp", "volume"}`` records ready for
    ``_weekly_bins``.
    """
    timestamps = node_history.get("timestamps", [])
    total_potential_generated = node_history.get("total_potential_generated", {})
    increments_per_step = [0.0] * len(timestamps)
    for cumulative_series in total_potential_generated.values():
        previous_cumulative = 0.0
        for step_index in range(min(len(timestamps), len(cumulative_series))):
            increment = cumulative_series[step_index] - previous_cumulative
            previous_cumulative = cumulative_series[step_index]
            increments_per_step[step_index] += increment
    return [
        {"timestamp": timestamps[step_index], "volume": increments_per_step[step_index]}
        for step_index in range(len(timestamps))
    ]


def generation_floor_cv2(
    generation_history: Dict[str, Dict[str, Any]]
) -> Optional[float]:
    """Source-variance floor (ADR 0005): volume-weighted CV^2 of weekly waste
    generation across generator nodes.

    A reference value, not an echelon ratio -- a raw CV^2 (not normalized against
    consumption) that the echelon ratios amplify above; policy-invariant because
    generators do not order. Per node: CV^2 of weekly potential generated volume
    (cumulative ``total_potential_generated`` differenced into weekly increments),
    averaged weighted by each node's mean weekly generation so a near-zero-volume
    node cannot dominate. Returns ``None`` when no node yields a defined,
    positive-volume CV^2.
    """
    weighted_cv_squared_sum = 0.0
    weight_total = 0.0
    for node_name in sorted(generation_history):
        node_bins = _weekly_bins(
            _generation_increment_records(generation_history[node_name]), "volume"
        )
        node_cv_squared = cv_squared(node_bins)
        if node_cv_squared is None:
            continue
        mean_weekly_generation = sum(node_bins) / len(node_bins)
        if mean_weekly_generation <= 0:
            continue
        weighted_cv_squared_sum += node_cv_squared * mean_weekly_generation
        weight_total += mean_weekly_generation

    if weight_total == 0:
        return None
    return weighted_cv_squared_sum / weight_total


def _echelon_anchored_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
    source_type: str,
    target_type: str,
) -> Optional[float]:
    """Volume-weighted throughput bullwhip for one ordering echelon, one run.

    The echelon is the ``source_type -> target_type`` flow link, its ordering node
    the ``target_name``. Per node: CV^2 of weekly inbound flow over CV^2 of the
    shared weekly consumption-``attempted`` anchor (never ``consumed``; ADR 0004).
    Per-node ratios are averaged weighted by mean weekly inbound flow so a
    near-zero-flow node cannot dominate. Returns ``None`` when the anchor is
    undefined or no node yields a defined, positive-flow ratio.
    """
    consumption_bins = _weekly_bins(consumption_events, "attempted")
    if cv_squared(consumption_bins) in (None, 0):
        return None

    inbound_flows_by_node: Dict[str, List[Dict[str, Any]]] = {}
    for flow in transport_flows:
        if flow.get("source_type") == source_type and flow.get("target_type") == target_type:
            inbound_flows_by_node.setdefault(flow["target_name"], []).append(flow)

    weighted_ratio_sum = 0.0
    weight_total = 0.0
    for node_name in sorted(inbound_flows_by_node):
        node_bins = _weekly_bins(inbound_flows_by_node[node_name], "volume")
        node_ratio = bullwhip_ratio(node_bins, consumption_bins)
        if node_ratio is None:
            continue
        mean_weekly_inbound_flow = sum(node_bins) / len(node_bins)
        if mean_weekly_inbound_flow <= 0:
            continue
        weighted_ratio_sum += node_ratio * mean_weekly_inbound_flow
        weight_total += mean_weekly_inbound_flow

    if weight_total == 0:
        return None
    return weighted_ratio_sum / weight_total


def treatment_anchored_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
) -> Optional[float]:
    """Treatment-echelon throughput bullwhip: the ``collector->treatment`` link.

    Each treatment operator's inbound waste flow against the consumption anchor.
    See ``_echelon_anchored_bullwhip`` for the binning and weighting.
    """
    return _echelon_anchored_bullwhip(
        transport_flows, consumption_events, "collector", "treatment"
    )


def collector_anchored_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
) -> Optional[float]:
    """Collector-echelon throughput bullwhip: the ``generator->collector`` link.

    The upstream ordering echelon -- each collector's inbound waste flow from
    generators against the same exogenous consumption anchor as Treatment.
    See ``_echelon_anchored_bullwhip`` for the binning and weighting.
    """
    return _echelon_anchored_bullwhip(
        transport_flows, consumption_events, "generator", "collector"
    )


def _pooled_inbound_bins(
    transport_flows: Sequence[Dict[str, Any]], source_type: str, target_type: str
) -> List[float]:
    """Weekly inbound-flow bins for one echelon, pooled across all of its nodes.

    The stage-by-stage diagnostic (ADR 0006) needs each echelon reduced to a
    single CV^2 scalar so the stage ratios telescope exactly. Pooling sums every
    ``source_type -> target_type`` flow into one weekly series (rather than
    grouping by ``target_name`` as the per-node anchored metric does), reusing
    the same ``_weekly_bins`` window and warm-up cut -- no second binning scheme.
    """
    echelon_flows = [
        flow
        for flow in transport_flows
        if flow.get("source_type") == source_type
        and flow.get("target_type") == target_type
    ]
    return _weekly_bins(echelon_flows, "volume")


def stage_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    """Stage-by-stage throughput-bullwhip diagnostic (ADR 0004, refined ADR 0006).

    Localizes WHERE amplification is injected by splitting the chain into two
    composable stage ratios, each on the system-pooled per-echelon weekly series
    (all nodes summed before CV^2) so each echelon is a single CV^2 value:

    - ``treatment_stage`` = ``CV^2(pooled collector->treatment inbound) /
      CV^2(consumption attempted)``
    - ``collector_stage`` = ``CV^2(pooled generator->collector inbound) /
      CV^2(pooled collector->treatment inbound)``

    The stages telescope exactly to the pooled collector anchored ratio (the
    pooled treatment-inbound CV^2 cancels) -- but only at this pooled aggregation,
    not the per-node volume-weighted headline, so ``treatment_stage`` is NOT the
    ``treatment_anchored`` headline (ADR 0006). Returns ``(treatment_stage,
    collector_stage)``; either is ``None`` when its denominator CV^2 is undefined
    or zero (see ``bullwhip_ratio``).
    """
    consumption_bins = _weekly_bins(consumption_events, "attempted")
    treatment_inbound_bins = _pooled_inbound_bins(
        transport_flows, "collector", "treatment"
    )
    collector_inbound_bins = _pooled_inbound_bins(
        transport_flows, "generator", "collector"
    )
    treatment_stage = bullwhip_ratio(treatment_inbound_bins, consumption_bins)
    collector_stage = bullwhip_ratio(collector_inbound_bins, treatment_inbound_bins)
    return treatment_stage, collector_stage


def pooled_anchored_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
    source_type: str,
    target_type: str,
) -> Optional[float]:
    """System-pooled anchored throughput bullwhip for one echelon (ADR 0007).

    The robustness variant of ``_echelon_anchored_bullwhip``: sums every
    ``source_type -> target_type`` flow into one pooled weekly series
    (``_pooled_inbound_bins``), then takes its CV^2 over the shared
    consumption-``attempted`` anchor. Pooling understates the per-node headline, so
    it is a conservative lower bound. For the Treatment echelon it equals
    ``stage_bullwhip``'s ``treatment_stage`` by construction (ADR 0006); the
    Collector value equals the telescoped stage product. Returns ``None`` when the
    anchor is undefined or flat, or the pooled flow CV^2 is undefined (see
    ``bullwhip_ratio``).
    """
    consumption_bins = _weekly_bins(consumption_events, "attempted")
    pooled_inbound_bins = _pooled_inbound_bins(
        transport_flows, source_type, target_type
    )
    return bullwhip_ratio(pooled_inbound_bins, consumption_bins)


def treatment_anchored_pooled_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
) -> Optional[float]:
    """Pooled Treatment-echelon robustness variant: the ``collector->treatment``
    link, all operators summed before CV^2.

    Coincides by construction with ``stage_bullwhip``'s ``treatment_stage``
    (ADR 0006, 0007). See ``pooled_anchored_bullwhip``.
    """
    return pooled_anchored_bullwhip(
        transport_flows, consumption_events, "collector", "treatment"
    )


def collector_anchored_pooled_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
) -> Optional[float]:
    """Pooled Collector-echelon robustness variant: the ``generator->collector``
    link, all collectors summed before CV^2.

    Unlike the Treatment pooled value, this matches no single stage ratio; it
    equals the telescoped product ``treatment_stage * collector_stage`` (ADR 0007).
    See ``pooled_anchored_bullwhip``.
    """
    return pooled_anchored_bullwhip(
        transport_flows, consumption_events, "generator", "collector"
    )
