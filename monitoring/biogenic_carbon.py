"""Biogenic carbon stored in produced panels (static credit, C10).

A purely post-hoc accounting metric: each cubic metre of MDF / particle board /
OSB the system produces locks up the biogenic carbon embodied in that panel for
the product's lifetime. The metric rescales the already-recorded cumulative
production volume per output type by that product's per-m3 biogenic carbon stock;
it does not touch the simulation, so adding it keeps the golden additive exit test
valid.

This is the STATIC, production-weighted credit -- NOT the time-integrated /
dynamic GWP-bio view (Levasseur dynamic LCA), which characterises biogenic CO2 by
how long carbon is stored before release and so needs a product service-life +
end-of-life release profile the model does not have (it stops at Market
Consumption). That view is deferred (see the C10 ticket); a constant-rescaled
static stock must not be called GWP-bio.

Sign convention follows ``ProductSpecification.biogenic_carbon_stock``: NEGATIVE
means carbon sequestered (held out of the atmosphere), so the stored credit reads
negative beside the positive operational ``total_emissions_kgco2e``. The three
carbon lines are orthogonal and reported beside each other, never netted (ADR
0011): biogenic carbon is excluded from ``total_emissions_kgco2e`` and the C11
avoided-emissions factors are biogenic-excluded too, so this credit does not
double-count either.

Reported under the shared ``carbon`` namespace so it rides the generic Monte Carlo
aggregation + CRN paired machinery (issues 06/07) the same way ``bullwhip`` and
``residence`` do -- the namespace is already wired, alongside C11's avoided
emissions.

Cumulative production per output type is read from
``processing_history[name]["products"]["by_type"][product]`` -- the last sample is
the end-of-run cumulative volume -- summed across all treatment operators (the
shared reader in ``monitoring.avoided_emissions``).
"""
from __future__ import annotations

from typing import Any, Dict

from models.products import ProductDataManager
from monitoring.avoided_emissions import total_produced_by_product


# Output products carrying a biogenic-carbon stored credit, in display order.
# Mirrors the avoided-emissions product order so the two carbon lines read in
# parallel under the shared `carbon` namespace.
_PRODUCTS = ("mdf", "particle_board", "osb")


def _biogenic_stock_by_product() -> Dict[str, float]:
    """Per-m3 biogenic carbon stock per output type (negative = sequestered).

    Read from the single ``ProductSpecification`` source (``models/products.py``),
    not duplicated into ``constants.py`` -- the same literals already back
    ``core.treatment.calculate_total_biogenic_carbon_stored``, and a second copy
    would be a silent drift risk.
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
