"""Biogenic carbon stored in produced panels (static credit, C10).

A post-hoc accounting metric: rescales the already-recorded cumulative production
volume per output type by that product's per-m3 biogenic carbon stock. It does
not touch the simulation, so adding it keeps the golden additive exit test valid.
The **Biogenic Carbon Stored** glossary term (CONTEXT.md) defines the static
credit -- negative = sequestered, one of three orthogonal carbon lines reported
beside, never netted with, the others (ADR 0011), and explicitly NOT the dynamic
GWP-bio view. Emitted under the shared ``carbon`` namespace beside C11's avoided
emissions so it rides the generic MC aggregation + CRN machinery (issues 06/07).

Cumulative production per output type is read via the shared reader in
``analysis.avoided_emissions`` (last sample = end-of-run cumulative volume),
summed across all treatment operators.
"""
from __future__ import annotations

from typing import Any, Dict

from models.products import ProductDataManager
from .avoided_emissions import total_produced_by_product


# Output products carrying a biogenic-carbon stored credit, in display order.
# Mirrors the avoided-emissions product order so the two carbon lines read in
# parallel under the shared `carbon` namespace.
_PRODUCTS = ("mdf", "particle_board", "osb")


def _biogenic_stock_by_product() -> Dict[str, float]:
    """Per-m3 biogenic carbon stock per output type (negative = sequestered).

    Read from the single ``ProductSpecification`` source (``models/products.py``)
    rather than duplicated into ``constants.py``.
    """
    manager = ProductDataManager()
    stock: Dict[str, float] = {}
    for product in _PRODUCTS:
        spec = manager.get_product_specification(product)
        stock[product] = spec.biogenic_carbon_stock if spec else 0.0
    return stock


def biogenic_carbon_metrics(monitor_data: Dict[str, Any]) -> Dict[str, float]:
    """Biogenic carbon stored (kg CO2e) per output type and total, negative-signed.

    NEGATIVE = carbon sequestered out of the atmosphere (the
    ``ProductSpecification.biogenic_carbon_stock`` convention). Keys are
    ``biogenic_carbon_stored_{product}_kgco2e`` for each output type in display
    order, then ``biogenic_carbon_stored_total_kgco2e``.
    """
    produced = total_produced_by_product(monitor_data, _PRODUCTS)
    stock = _biogenic_stock_by_product()
    metrics: Dict[str, float] = {}
    total = 0.0
    for product in _PRODUCTS:
        stored = produced[product] * stock[product]
        metrics[f"biogenic_carbon_stored_{product}_kgco2e"] = stored
        total += stored
    metrics["biogenic_carbon_stored_total_kgco2e"] = total
    return metrics
