"""Collection rate divides by treatable generation; outlet waste is split by SURS destination (ADR 0036)."""
import json

import pytest

from analysis.baseline_aggregate import extract_kpis
from analysis.outlet import OUTLET_SHARES_PATH


def _monitor_data():
    return {
        "generation_history": {"gen-1": {
            "total_generated": {"17 02 01": [100.0], "20 03 07": [0.0]},
            "total_potential_generated": {"17 02 01": [100.0], "20 03 07": [300.0]},
            "total_uncollected": {"17 02 01": [0.0], "20 03 07": [0.0]},
            "total_outlet": {"17 02 01": [0.0], "20 03 07": [300.0]},
        }},
        "collection_history": {"col-1": {"collected_volumes": {"17 02 01": [50.0]}}},
    }


def test_collection_rate_excludes_outlet_waste_from_the_denominator():
    """Mutation check (red): divide collection_rate_pct by all potential generation."""
    kpis = extract_kpis(_monitor_data())

    assert kpis["outlet_volume_m3"] == pytest.approx(300.0)
    assert kpis["collection_rate_pct"] == pytest.approx(50.0)
    assert kpis["collection_rate_all_generation_pct"] == pytest.approx(12.5)


def test_outlet_volume_is_split_by_surs_destination_shares():
    """Mutation check (red): send all outlet volume to one destination."""
    shares = json.loads(OUTLET_SHARES_PATH.read_text())["20 03 07"]

    by_destination = extract_kpis(_monitor_data())["outlet_by_destination"]

    for destination, share in shares.items():
        assert by_destination[f"{destination}_m3"] == pytest.approx(300.0 * share)
    assert sum(by_destination.values()) == pytest.approx(300.0)
