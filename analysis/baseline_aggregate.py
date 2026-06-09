from __future__ import annotations
import math
from typing import Dict, Any, List

from .bullwhip import (
    collector_anchored_bullwhip,
    collector_anchored_pooled_bullwhip,
    generation_floor_cv2,
    stage_bullwhip,
    treatment_anchored_bullwhip,
    treatment_anchored_pooled_bullwhip,
)
from .flow_times import flow_time_metrics
from .avoided_emissions import avoided_emissions_metrics
from .biogenic_carbon import biogenic_carbon_metrics
from ._kpi_shared import _GENERIC_NAMESPACES, t_ci_margin


# Marginal KPIs aggregated into summary.csv, in display order. The nested
# `bullwhip` namespace is appended generically afterward (issue 06).
_SUMMARY_METRICS = [
    "total_generated_m3",
    "total_collected_m3",
    "total_processed_m3",
    "collection_rate_pct",
    "processing_rate_pct",
    "overall_efficiency_pct",
    "landfill_volume_m3",
    "total_emissions_kgco2e",
    "collection_transport_cost",
    "processing_cost",
    "storage_overflow_cost",
    "total_system_cost",
    "max_collector_util_pct",
    "max_processor_waste_util_pct",
    "max_processor_finished_goods_util_pct",
    "service_level_full_pct",
    "service_level_operational_pct",
    "total_attempted_m3",
    "total_consumed_m3",
    "no_capability_lost_m3",
    "stockout_lost_m3",
]

_SUMMARY_HEADER = "metric,mean,stdev,ci95_low,ci95_high,count"


def _mean_ci(vals: List[float], alpha: float):
    """Mean, sample stdev, and two-sided Student-t CI of ``vals``.

    Variance is estimated from the sample, so the textbook small-n interval is
    Student-t with ``n-1`` degrees of freedom (ADR 0008), matching the paired
    comparison machinery. A single observation has no spread: stdev 0 and the
    CI collapses to the mean (``t.ppf`` is undefined at zero df).
    """
    n = len(vals)
    mean = sum(vals) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in vals) / (n - 1)
        stdev = math.sqrt(var)
        margin = t_ci_margin(n, stdev, alpha)
        return mean, stdev, mean - margin, mean + margin
    return mean, 0.0, mean, mean


def summary_rows(kpis_list: List[Dict[str, Any]], alpha: float = 0.05) -> List[str]:
    """Build the ``summary.csv`` rows (header first) for one combo's replications.

    Each marginal KPI in ``_SUMMARY_METRICS`` becomes a mean + Student-t CI row
    over the replications that reported it (``None`` excluded; all-``None`` keys
    skipped). Pure and free of I/O so it can be unit-tested without a run.
    """
    rows = [_SUMMARY_HEADER]
    if not kpis_list:
        return rows
    for metric in _SUMMARY_METRICS:
        vals = [float(k[metric]) for k in kpis_list if k.get(metric) is not None]
        if not vals:
            continue
        mean, stdev, lo, hi = _mean_ci(vals, alpha)
        rows.append(
            f"{metric},{mean:.6g},{stdev:.6g},{lo:.6g},{hi:.6g},{len(vals)}"
        )

    # Generic pass: aggregate whatever keys exist in each nested namespace so new
    # variants flow through with no wiring here (issue 06). Keys are discovered as
    # an insertion-ordered union across replications, surviving a partial dict.
    for namespace in _GENERIC_NAMESPACES:
        namespace_keys: Dict[str, None] = {}
        for k in kpis_list:
            for key in k.get(namespace, {}) or {}:
                namespace_keys.setdefault(key, None)
        for key in namespace_keys:
            vals = [
                float(k[namespace][key])
                for k in kpis_list
                if (k.get(namespace) or {}).get(key) is not None
            ]
            if not vals:
                # Degenerate across every replication: emit the row anyway with
                # count 0 and blank stats so the namespace stays discoverable.
                rows.append(f"{namespace}.{key},,,,,0")
                continue
            mean, stdev, lo, hi = _mean_ci(vals, alpha)
            rows.append(
                f"{namespace}.{key},{mean:.6g},{stdev:.6g},{lo:.6g},{hi:.6g},{len(vals)}"
            )
    return rows


def _sum_last_nested(histories: Dict[str, Any], key: str) -> float:
    total = 0.0
    for hist in histories.values():
        data = hist.get(key, {})
        if isinstance(data, dict):
            for series in data.values():
                if isinstance(series, list) and series:
                    total += float(series[-1])
        elif isinstance(data, list) and data:
            total += float(data[-1])
    return total


def _sum_series(series: Any) -> float:
    # Cost series hold the cost incurred per tracking step (not a running
    # cumulative), so the entity total is the sum over the whole series.
    return float(sum(series)) if isinstance(series, list) else 0.0


def extract_kpis(monitor_data: Dict[str, Any]) -> Dict[str, Any]:
    gen_hist = monitor_data.get("generation_history", {})
    col_hist = monitor_data.get("collection_history", {})
    proc_hist = monitor_data.get("processing_history", {})
    env_hist = monitor_data.get("environmental_history", {})
    evt_hist = monitor_data.get("event_history", {})
    final_summary = monitor_data.get("final_summary", {})

    total_generated = _sum_last_nested(gen_hist, "total_generated")
    total_collected = _sum_last_nested(col_hist, "collected_volumes")

    total_processed = 0.0
    for hist in proc_hist.values():
        series = hist.get("processed", {}).get("total", [])
        if isinstance(series, list) and series:
            total_processed += float(series[-1])

    collection_rate = (
        (total_collected / total_generated * 100.0) if total_generated > 0 else 0.0
    )
    processing_rate = (
        (total_processed / total_collected * 100.0) if total_collected > 0 else 0.0
    )
    overall_eff = (
        (total_processed / total_generated * 100.0) if total_generated > 0 else 0.0
    )

    landfill_volume = 0.0
    sys_evt = evt_hist.get("system_events", {})
    if sys_evt:
        landfill_volume = float(sum(sys_evt.get("landfill_usage", []) or []))

    # Emissions
    total_emissions = 0.0
    for hist in env_hist.values():
        series = hist.get("total_impact", [])
        if isinstance(series, list) and series:
            total_emissions += float(series[-1])

    # System cost (section 4.4): total system cost across collection/transport,
    # processing, and storage. Each entity's per-step total_costs series is
    # summed; the three component totals add to total_system_cost.
    collection_transport_cost = sum(
        _sum_series(hist.get("total_costs")) for hist in col_hist.values()
    )
    processing_cost = sum(
        _sum_series(hist.get("operational", {}).get("total_costs"))
        for hist in proc_hist.values()
    )
    storage_overflow_cost = _sum_series(
        evt_hist.get("system_events", {}).get("total_costs")
    )
    total_system_cost = (
        collection_transport_cost + processing_cost + storage_overflow_cost
    )

    # Storage utilizations
    max_collector_util = 0.0
    for hist in col_hist.values():
        series = hist.get("storage_utilization", [])
        if series:
            max_collector_util = max(max_collector_util, float(max(series)))

    max_processor_waste_util = 0.0
    max_processor_finished_goods_util = 0.0
    for hist in proc_hist.values():
        storage_data = hist.get("storage", {})
        waste_util = storage_data.get("waste_utilization", [])
        finished_goods_util = storage_data.get("finished_goods_utilization", [])
        if waste_util:
            max_processor_waste_util = max(
                max_processor_waste_util, float(max(waste_util))
            )
        if finished_goods_util:
            max_processor_finished_goods_util = max(
                max_processor_finished_goods_util, float(max(finished_goods_util))
            )

    # Continuous market-consumption service levels (ADR 0002). None when no
    # consumption was attempted (undefined, not zero); fractions -> percent.
    def _pct(fraction):
        return fraction * 100.0 if fraction is not None else None

    service_level_full = _pct(final_summary.get("full_service_level"))
    service_level_operational = _pct(final_summary.get("operational_service_level"))
    service_level_full_by_product = {
        product_name: _pct(value)
        for product_name, value in (final_summary.get("consumption_service_by_product") or {}).items()
    }

    # Throughput bullwhip (ADR 0004-0007), post-hoc from the run logs, under a
    # `bullwhip` namespace so later slices extend it without rewiring this dict.
    # See analysis/bullwhip.py for what each key measures.
    transport_flows = monitor_data.get("transport_flows", [])
    consumption_events = monitor_data.get("consumption_events", [])
    treatment_stage, collector_stage = stage_bullwhip(
        transport_flows, consumption_events
    )
    bullwhip = {
        "treatment_anchored": treatment_anchored_bullwhip(
            transport_flows, consumption_events
        ),
        "collector_anchored": collector_anchored_bullwhip(
            transport_flows, consumption_events
        ),
        "treatment_stage": treatment_stage,
        "collector_stage": collector_stage,
        "treatment_anchored_pooled": treatment_anchored_pooled_bullwhip(
            transport_flows, consumption_events
        ),
        "collector_anchored_pooled": collector_anchored_pooled_bullwhip(
            transport_flows, consumption_events
        ),
        "generation_floor_cv2": generation_floor_cv2(gen_hist),
    }

    return {
        "total_generated_m3": total_generated,
        "total_collected_m3": total_collected,
        "total_processed_m3": total_processed,
        "collection_rate_pct": collection_rate,
        "processing_rate_pct": processing_rate,
        "overall_efficiency_pct": overall_eff,
        "landfill_volume_m3": landfill_volume,
        "total_emissions_kgco2e": total_emissions,
        "collection_transport_cost": collection_transport_cost,
        "processing_cost": processing_cost,
        "storage_overflow_cost": storage_overflow_cost,
        "total_system_cost": total_system_cost,
        "max_collector_util_pct": max_collector_util,
        "max_processor_waste_util_pct": max_processor_waste_util,
        "max_processor_finished_goods_util_pct": max_processor_finished_goods_util,
        "service_level_full_pct": service_level_full,
        "service_level_operational_pct": service_level_operational,
        "service_level_full_by_product_pct": service_level_full_by_product,
        "total_attempted_m3": float(final_summary.get("total_attempted_consumption") or 0.0),
        "total_consumed_m3": float(final_summary.get("total_consumed") or 0.0),
        "no_capability_lost_m3": float(final_summary.get("no_capability_lost") or 0.0),
        "stockout_lost_m3": float(final_summary.get("stockout_lost") or 0.0),
        "bullwhip": bullwhip,
        # Lead and residence times (Little's Law, C4): per-stage WIP, throughput,
        # and residence, post-hoc from monitor history.
        "residence": flow_time_metrics(monitor_data),
        # Carbon credits (ADR 0011), production-weighted, reported beside
        # total_emissions_kgco2e and never netted: avoided emissions (C11) and
        # biogenic carbon stored (C10). Distinct key prefixes keep them apart.
        "carbon": {
            **avoided_emissions_metrics(monitor_data),
            **biogenic_carbon_metrics(monitor_data),
        },
    }
