"""Tests for avoided-emissions metrics (recycling avoided-burden, C11, ADR 0011).

Exercises monitoring.avoided_emissions against a synthetic monitor_data whose
per-operator cumulative production is chosen so the avoided figures are round
multiples of the Lao 2023 factors. Mirrors the inline-synthetic-dict style of
test_flow_times.py / test_bullwhip.py -- no simulation run.
"""

import pytest

from config.constants import AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT
from monitoring.avoided_emissions import avoided_emissions_metrics


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


def test_each_product_is_rescaled_by_its_own_factor():
    md = _monitor_data(
        [{"mdf": [0.0, 10.0], "particle_board": [0.0, 20.0], "osb": [0.0, 5.0]}]
    )
    m = avoided_emissions_metrics(md)
    assert m["avoided_emissions_mdf_kgco2e"] == pytest.approx(10.0 * 406.0)
    assert m["avoided_emissions_particle_board_kgco2e"] == pytest.approx(20.0 * 348.0)
    assert m["avoided_emissions_osb_kgco2e"] == pytest.approx(5.0 * 552.0)


def test_total_is_the_sum_across_products():
    md = _monitor_data([{"mdf": [10.0], "particle_board": [20.0], "osb": [5.0]}])
    m = avoided_emissions_metrics(md)
    expected = 10.0 * 406.0 + 20.0 * 348.0 + 5.0 * 552.0
    assert m["avoided_emissions_total_kgco2e"] == pytest.approx(expected)


def test_production_sums_across_operators_using_the_last_sample():
    md = _monitor_data([{"mdf": [0.0, 4.0]}, {"mdf": [0.0, 6.0]}])
    m = avoided_emissions_metrics(md)
    # 4 + 6 = 10 m3 of MDF across the two operators; only the final sample counts.
    assert m["avoided_emissions_mdf_kgco2e"] == pytest.approx(10.0 * 406.0)


def test_empty_monitor_data_is_all_zero():
    m = avoided_emissions_metrics({})
    for product in AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT:
        assert m[f"avoided_emissions_{product}_kgco2e"] == 0.0
    assert m["avoided_emissions_total_kgco2e"] == 0.0


def test_avoided_emissions_are_positive_signed():
    md = _monitor_data([{"osb": [3.0]}])
    m = avoided_emissions_metrics(md)
    assert m["avoided_emissions_osb_kgco2e"] > 0
    assert m["avoided_emissions_total_kgco2e"] > 0
