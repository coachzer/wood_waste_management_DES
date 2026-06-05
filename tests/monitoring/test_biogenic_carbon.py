"""Tests for the biogenic-carbon stored credit (static, C10).

Exercises monitoring.biogenic_carbon against a synthetic monitor_data whose
per-operator cumulative production is chosen so the stored figures are round
multiples of the per-product ProductSpecification.biogenic_carbon_stock. Mirrors
the inline-synthetic-dict style of test_avoided_emissions.py -- no simulation run.

The biogenic stock is read from the single ProductSpecification source rather
than hardcoded, so these tests track that source if the literals are ever
revised; they pin the wiring (driver, summation, sign), not the magnitudes.
"""

import pytest

from models.products import ProductDataManager
from monitoring.biogenic_carbon import biogenic_carbon_metrics


_STOCK = {
    product: ProductDataManager().get_product_specification(product).biogenic_carbon_stock
    for product in ("mdf", "particle_board", "osb")
}


def _monitor_data(per_operator):
    """Build a monitor_data carrying only products.by_type series per operator.

    ``per_operator`` is a list of ``{product: [cumulative series]}`` dicts, one
    per treatment operator.
    """
    return {
        "processing_history": {
            f"op{i}": {"products": {"by_type": by_type}}
            for i, by_type in enumerate(per_operator)
        }
    }


def test_each_product_is_rescaled_by_its_own_biogenic_stock():
    md = _monitor_data(
        [{"mdf": [0.0, 10.0], "particle_board": [0.0, 20.0], "osb": [0.0, 5.0]}]
    )
    m = biogenic_carbon_metrics(md)
    assert m["biogenic_carbon_stored_mdf_kgco2e"] == pytest.approx(10.0 * _STOCK["mdf"])
    assert m["biogenic_carbon_stored_particle_board_kgco2e"] == pytest.approx(
        20.0 * _STOCK["particle_board"]
    )
    assert m["biogenic_carbon_stored_osb_kgco2e"] == pytest.approx(5.0 * _STOCK["osb"])


def test_total_is_the_sum_across_products():
    md = _monitor_data([{"mdf": [10.0], "particle_board": [20.0], "osb": [5.0]}])
    m = biogenic_carbon_metrics(md)
    expected = 10.0 * _STOCK["mdf"] + 20.0 * _STOCK["particle_board"] + 5.0 * _STOCK["osb"]
    assert m["biogenic_carbon_stored_total_kgco2e"] == pytest.approx(expected)


def test_production_sums_across_operators_using_the_last_sample():
    md = _monitor_data([{"mdf": [0.0, 4.0]}, {"mdf": [0.0, 6.0]}])
    m = biogenic_carbon_metrics(md)
    # 4 + 6 = 10 m3 of MDF across the two operators; only the final sample counts.
    assert m["biogenic_carbon_stored_mdf_kgco2e"] == pytest.approx(10.0 * _STOCK["mdf"])


def test_empty_monitor_data_is_all_zero():
    m = biogenic_carbon_metrics({})
    for product in ("mdf", "particle_board", "osb"):
        assert m[f"biogenic_carbon_stored_{product}_kgco2e"] == 0.0
    assert m["biogenic_carbon_stored_total_kgco2e"] == 0.0


def test_stored_credit_is_negative_signed_sequestration():
    # ProductSpecification.biogenic_carbon_stock is negative (carbon sequestered
    # out of the atmosphere); produced volume is non-negative, so the credit
    # reads negative beside the positive total_emissions_kgco2e.
    md = _monitor_data([{"osb": [3.0]}])
    m = biogenic_carbon_metrics(md)
    assert m["biogenic_carbon_stored_osb_kgco2e"] < 0
    assert m["biogenic_carbon_stored_total_kgco2e"] < 0
