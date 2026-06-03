"""Throughput-bullwhip measurement (ADR 0004).

A purely post-hoc metric: it reads the already-persisted ``transport_flows`` and
``consumption_events`` logs of a single run and computes a CV^2-normalized
flow-amplification ratio. It does not touch the simulation, so adding it keeps
the golden byte-identical exit test valid.

The module is layered so the arithmetic core (``cv_squared``,
``bullwhip_ratio``) has no simulation or I/O dependency -- it takes plain numeric
sequences and is the natural unit-test seam. ``_echelon_anchored_bullwhip``
sits on top, doing the weekly binning and per-node volume-weighted aggregation
for one ordering echelon; ``treatment_anchored_bullwhip`` (collector->treatment)
and ``collector_anchored_bullwhip`` (generator->collector) are thin wrappers that
pick the flow link. Both anchor on the same exogenous consumption series.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from config.constants import (
    BULLWHIP_BIN_WIDTH_DAYS,
    BULLWHIP_WARMUP_WEEKS,
    WEEKS_PER_YEAR,
)


def cv_squared(series: Sequence[float]) -> Optional[float]:
    """Squared coefficient of variation: ``var / mean**2`` (population variance).

    The unit-free dispersion measure underlying the throughput-bullwhip ratio
    (ADR 0004): normalizing by the mean makes it comparable across the
    waste->product commodity change and across the asymmetric regional volumes.
    Returns ``None`` where it is undefined -- fewer than two bins (no dispersion
    to measure) or a zero mean (the normalization explodes).
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
    bins. The window spans 0-based week indices BULLWHIP_WARMUP_WEEKS ..
    WEEKS_PER_YEAR - 1 (i.e. weeks 5-52 after dropping the 4-week cold-start
    ramp). Every week in the window gets a bin -- empty weeks stay 0.0 -- so a
    lumpy reorder spike registers as dispersion against the quiet weeks around
    it. Records outside the window (warm-up, or the trailing partial week) are
    ignored.
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


def _echelon_anchored_bullwhip(
    transport_flows: Sequence[Dict[str, Any]],
    consumption_events: Sequence[Dict[str, Any]],
    source_type: str,
    target_type: str,
) -> Optional[float]:
    """Volume-weighted throughput bullwhip for one ordering echelon, one run.

    The echelon is the ``source_type -> target_type`` flow link; its ordering
    node is the ``target_name`` (the entity pulling inbound flow). Per node:
    CV^2 of its weekly inbound flow over the CV^2 of the shared weekly
    market-consumption anchor. The anchor is consumption ``attempted`` (the
    exogenous demand presented to operators) -- never ``consumed``, which the
    system's own stockouts would deflate (ADR 0004). The per-node ratios are
    averaged weighted by each node's mean weekly inbound flow, so a
    near-zero-flow node whose CV^2 blows up cannot dominate.

    Returns ``None`` when the anchor is undefined or no node yields a defined,
    positive-flow ratio.
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
