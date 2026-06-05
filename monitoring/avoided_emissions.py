"""Avoided emissions from recycling avoided-burden (C11, ADR 0011).

A purely post-hoc accounting metric: every cubic metre of MDF / particle board /
OSB the system produces from recovered wood waste stands in for a functionally
identical panel that would otherwise have been manufactured from virgin
feedstock, so that panel's cradle-to-gate production footprint is avoided. The
metric rescales the already-recorded cumulative production volume per output type
by a fixed per-product factor; it does not touch the simulation, so adding it
keeps the golden additive exit test valid.

This is a recycling avoided-burden (secondary-vs-primary production of the *same*
good), NOT material substitution (a wood panel displacing concrete/steel): the
model has no non-wood counterfactual, so the latter claim is unsupported (ADR
0011). The factors are Lao & Chang (2023) cradle-to-gate footprints with biogenic
carbon EXCLUDED -- the exclusion is binding so the biogenic carbon C10 reports as
its own stored-credit line is not double-counted.

The avoided figure is a full cradle-to-gate LCA of the displaced virgin panel and
is reported beside, never netted against, the narrower in-simulation
``total_emissions_kgco2e`` (incommensurable boundaries, ADR 0011). Reported under
a ``carbon`` namespace so it rides the generic Monte Carlo aggregation + CRN
paired machinery (issues 06/07) the same way ``bullwhip`` and ``residence`` do.

Cumulative production per output type is read from
``processing_history[name]["products"]["by_type"][product]`` -- the last sample is
the end-of-run cumulative volume -- summed across all treatment operators.
"""
from __future__ import annotations

from typing import Any, Dict

from config.constants import AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT


def _total_produced_by_product(monitor_data: Dict[str, Any]) -> Dict[str, float]:
    """Sum end-of-run cumulative production per output type across operators."""
    totals: Dict[str, float] = {
        product: 0.0 for product in AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT
    }
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
    produced = _total_produced_by_product(monitor_data)
    metrics: Dict[str, float] = {}
    total = 0.0
    for product, factor in AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT.items():
        avoided = produced[product] * factor
        metrics[f"avoided_emissions_{product}_kgco2e"] = avoided
        total += avoided
    metrics["avoided_emissions_total_kgco2e"] = total
    return metrics
