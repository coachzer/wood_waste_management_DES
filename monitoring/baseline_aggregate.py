from __future__ import annotations
from typing import Dict, Any


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

    # Events: landfill volume
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

    # Storage utilizations
    max_collector_util = 0.0
    for hist in col_hist.values():
        series = hist.get("storage_utilization", [])
        if series:
            max_collector_util = max(max_collector_util, float(max(series)))

    max_processor_waste_util = 0.0
    max_processor_product_util = 0.0
    for hist in proc_hist.values():
        s = hist.get("storage", {})
        waste_util = s.get("waste_utilization", [])
        prod_util = s.get("product_utilization", [])
        if waste_util:
            max_processor_waste_util = max(
                max_processor_waste_util, float(max(waste_util))
            )
        if prod_util:
            max_processor_product_util = max(
                max_processor_product_util, float(max(prod_util))
            )

    # Service levels
    service_level_overall = None
    service_level_by_product = {}
    if final_summary:
        totals = final_summary.get("total_products", {}) or {}
        targets = final_summary.get("target_demands", {}) or {}
        total_out = sum(float(v) for v in totals.values())
        total_target = sum(float(v) for v in targets.values())
        service_level_overall = (
            (total_out / total_target * 100.0) if total_target > 0 else None
        )
        for p, tgt in targets.items():
            v = float(totals.get(p, 0.0))
            t = float(tgt)
            service_level_by_product[p] = (v / t * 100.0) if t > 0 else None

    return {
        "total_generated_m3": total_generated,
        "total_collected_m3": total_collected,
        "total_processed_m3": total_processed,
        "collection_rate_pct": collection_rate,
        "processing_rate_pct": processing_rate,
        "overall_efficiency_pct": overall_eff,
        "landfill_volume_m3": landfill_volume,
        "total_emissions_kgco2e": total_emissions,
        "max_collector_util_pct": max_collector_util,
        "max_processor_waste_util_pct": max_processor_waste_util,
        "max_processor_product_util_pct": max_processor_product_util,
        "service_level_overall_pct": service_level_overall,
        "service_level_by_product": service_level_by_product,
    }
