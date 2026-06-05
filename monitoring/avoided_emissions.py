"""Avoided emissions from recycling avoided-burden (C11, ADR 0011).

A post-hoc accounting metric: rescales the already-recorded cumulative production
volume per output type by a fixed per-product Lao & Chang (2023) cradle-to-gate
factor (biogenic-excluded). It does not touch the simulation, so adding it keeps
the golden additive exit test valid. The **Avoided Emissions** glossary term
(CONTEXT.md) defines the claim -- a recycling avoided-burden reported beside,
never netted against, ``total_emissions_kgco2e`` -- and ADR 0011 records why.
Emitted under a ``carbon`` namespace so it rides the generic MC aggregation + CRN
machinery (issues 06/07).

Cumulative production per output type is read from
``processing_history[name]["products"]["by_type"][product]`` (last sample = the
end-of-run cumulative volume), summed across all treatment operators.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from config.constants import AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT


def total_produced_by_product(
    monitor_data: Dict[str, Any], product_types: Iterable[str]
) -> Dict[str, float]:
    """Sum end-of-run cumulative production per output type across operators.

    Shared by the two production-weighted carbon credits (avoided emissions here,
    biogenic-stored in ``monitoring.biogenic_carbon``): both read the same
    ``products.by_type`` driver, so the reader lives once. ``product_types`` is
    the set of output types to total; any other key in the history is ignored.
    """
    totals: Dict[str, float] = {product: 0.0 for product in product_types}
    proc_hist = monitor_data.get("processing_history", {})
    for hist in proc_hist.values():
        by_type = hist.get("products", {}).get("by_type", {})
        for product, series in by_type.items():
            if product in totals and isinstance(series, list) and series:
                totals[product] += float(series[-1])
    return totals


def avoided_emissions_metrics(monitor_data: Dict[str, Any]) -> Dict[str, float]:
    """Avoided emissions (kg CO2eq) per output type and total, positive-signed.

    Keys are ``avoided_emissions_{product}_kgco2e`` for each output type in
    insertion order, then ``avoided_emissions_total_kgco2e``.
    """
    produced = total_produced_by_product(
        monitor_data, AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT
    )
    metrics: Dict[str, float] = {}
    total = 0.0
    for product, factor in AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT.items():
        avoided = produced[product] * factor
        metrics[f"avoided_emissions_{product}_kgco2e"] = avoided
        total += avoided
    metrics["avoided_emissions_total_kgco2e"] = total
    return metrics
