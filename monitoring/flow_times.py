"""Lead and residence times via Little's Law (C4).

A post-hoc metric family: for each waste-side storage stage (generator,
collection center, treatment) it reads the run's monitor history and computes
time-average WIP, throughput, and residence time. It does not touch the
simulation, so adding it keeps the golden additive exit test valid. The
**Time-Weighted WIP (Little's Law)** glossary term (CONTEXT.md) defines the
measure. Reported under a ``residence`` namespace so it rides the generic MC
aggregation + CRN machinery (issues 06/07). The arithmetic core
(``time_weighted_average``, ``residence_time``) is a sim/IO-free unit-test seam;
``_stage_*`` adapters read one stage's history and ``flow_time_metrics`` assembles
the namespace.

Inventory sources differ by stage. Treatment waste storage is recorded in
absolute m3 (``processing_history[name]["storage"]["total"]``). Generators and
collection centers are recorded only as utilization percent, so absolute
inventory is recovered as ``utilization% / 100 * capacity`` from the static
per-entity capacities in ``monitor_data["storage_capacities"]``. When those are
absent (e.g. a bare ``monitor_data`` in a unit test) stage WIP and residence are
``None``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from config.constants import SIMULATION_DURATION


def time_weighted_average(
    times: Sequence[float], levels: Sequence[float], horizon: float
) -> Optional[float]:
    """Time-average of an inventory level over ``[0, horizon]`` days.

    Treats the samples as a piecewise-linear level trace (trapezoidal area); the
    first sample holds flat back to ``t=0`` and the last flat forward to
    ``horizon`` so partial coverage does not bias the mean. Returns ``None`` for a
    non-positive horizon or no usable samples.
    """
    if horizon <= 0:
        return None
    points = sorted(
        (float(time), float(level))
        for time, level in zip(times, levels)
        if time is not None and level is not None
    )
    if not points:
        return None

    area = 0.0
    # Flat extrapolation before the first sample (level held constant from t=0).
    previous_time, previous_level = 0.0, points[0][1]
    for time, level in points:
        time = min(max(time, 0.0), horizon)
        if time > previous_time:
            area += (previous_level + level) / 2.0 * (time - previous_time)
        previous_time, previous_level = time, level
    # Flat extrapolation after the last sample to the horizon.
    if horizon > previous_time:
        area += previous_level * (horizon - previous_time)
    return area / horizon


def residence_time(
    wip: Optional[float], throughput: Optional[float]
) -> Optional[float]:
    """Average residence time in days = ``WIP / throughput`` (Little's Law).

    Returns ``None`` when WIP or throughput is undefined, or throughput is
    non-positive (no departures means residence is undefined, not infinite).
    """
    if wip is None or throughput is None or throughput <= 0:
        return None
    return wip / throughput


def _stage_wip_from_utilization(
    histories: Dict[str, Any], capacities: Dict[str, float], horizon: float
) -> Optional[float]:
    """Stage WIP (m3) for generators/collectors, summed over nodes.

    Recovers absolute inventory from each node's utilization-percent series via
    its static capacity (``util% / 100 * capacity`` -- the inverse of the
    ``* 100`` percent idiom in ``WasteMonitor._track_storage_metrics``). ``None``
    if no node yields a value (e.g. capacities missing).
    """
    if not histories or not capacities:
        return None
    total: Optional[float] = None
    for name, history in histories.items():
        capacity = capacities.get(name)
        if capacity is None:
            continue
        utilization = history.get("storage_utilization", [])
        timestamps = history.get("timestamps", [])
        levels = [percent / 100.0 * capacity for percent in utilization]
        node_average = time_weighted_average(timestamps, levels, horizon)
        if node_average is not None:
            total = (total or 0.0) + node_average
    return total


def _stage_wip_treatment(
    processing_history: Dict[str, Any], horizon: float
) -> Optional[float]:
    """Treatment-stage WIP (m3), summed over nodes, from the absolute storage
    series (no capacity needed -- recorded directly in m3)."""
    if not processing_history:
        return None
    total: Optional[float] = None
    for history in processing_history.values():
        levels = history.get("storage", {}).get("total", [])
        timestamps = history.get("timestamps", [])
        node_average = time_weighted_average(timestamps, levels, horizon)
        if node_average is not None:
            total = (total or 0.0) + node_average
    return total


def _throughput_from_flows(
    flows: List[Dict[str, Any]],
    horizon: float,
    source_type: str,
    target_type: Optional[str] = None,
) -> Optional[float]:
    """Departure rate (m3/day) over the run for one stage link.

    Sums shipment volumes on the matching ``source_type`` (and optional
    ``target_type``) link and divides by the horizon. ``None`` only when there
    are no flows at all; a zero sum yields a zero rate (and an undefined
    residence downstream)."""
    if not flows or horizon <= 0:
        return None
    total = sum(
        float(flow.get("volume", 0.0))
        for flow in flows
        if flow.get("source_type") == source_type
        and (target_type is None or flow.get("target_type") == target_type)
    )
    return total / horizon


def _treatment_throughput(
    processing_history: Dict[str, Any], horizon: float
) -> Optional[float]:
    """Treatment departure rate (m3/day): cumulative consumed waste (the corrected
    ADR-0009 intake, a terminal sink) over the horizon."""
    if not processing_history or horizon <= 0:
        return None
    total = 0.0
    for history in processing_history.values():
        series = history.get("processed", {}).get("total", [])
        if isinstance(series, list) and series:
            total += float(series[-1])
    return total / horizon


def flow_time_metrics(monitor_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Assemble the `residence` namespace: per-stage WIP, throughput, and
    residence time, plus the end-to-end storage residence (sum of stages).

    Every value is ``None`` for an empty ``monitor_data`` (degenerate guard,
    matching the bullwhip pattern)."""
    horizon = SIMULATION_DURATION
    capacities = monitor_data.get("storage_capacities", {}) or {}
    generation_history = monitor_data.get("generation_history", {})
    collection_history = monitor_data.get("collection_history", {})
    processing_history = monitor_data.get("processing_history", {})
    transport_flows = monitor_data.get("transport_flows", [])

    generator_wip = _stage_wip_from_utilization(
        generation_history, capacities.get("generators", {}), horizon
    )
    collector_wip = _stage_wip_from_utilization(
        collection_history, capacities.get("collectors", {}), horizon
    )
    treatment_wip = _stage_wip_treatment(processing_history, horizon)

    generator_throughput = _throughput_from_flows(
        transport_flows, horizon, "generator"
    )
    collector_throughput = _throughput_from_flows(
        transport_flows, horizon, "collector", "treatment"
    )
    treatment_throughput = _treatment_throughput(processing_history, horizon)

    generator_residence = residence_time(generator_wip, generator_throughput)
    collector_residence = residence_time(collector_wip, collector_throughput)
    treatment_residence = residence_time(treatment_wip, treatment_throughput)

    stage_residences = [
        value
        for value in (generator_residence, collector_residence, treatment_residence)
        if value is not None
    ]
    total_storage_residence = sum(stage_residences) if stage_residences else None

    return {
        "generator_wip_m3": generator_wip,
        "generator_throughput_m3_per_day": generator_throughput,
        "generator_residence_days": generator_residence,
        "collector_wip_m3": collector_wip,
        "collector_throughput_m3_per_day": collector_throughput,
        "collector_residence_days": collector_residence,
        "treatment_wip_m3": treatment_wip,
        "treatment_throughput_m3_per_day": treatment_throughput,
        "treatment_residence_days": treatment_residence,
        "total_storage_residence_days": total_storage_residence,
    }
