"""Collection and overall rates are shares of all generated waste, uncollected included (ADR 0024)."""
import pytest

from analysis.baseline_aggregate import extract_kpis


def _monitor_data(potential, entered_storage, collected):
    return {
        "generation_history": {"gen-1": {
            "total_generated": {"17 02 01": [entered_storage]},
            "total_potential_generated": {"17 02 01": [potential]},
            "total_uncollected": {"17 02 01": [potential - entered_storage]},
        }},
        "collection_history": {"col-1": {"collected_volumes": {"17 02 01": [collected]}}},
    }


def test_collection_rate_divides_by_potential_not_committed_generation():
    kpis = extract_kpis(_monitor_data(potential=200.0, entered_storage=100.0, collected=50.0))

    assert kpis["collection_rate_pct"] == pytest.approx(25.0)
    assert kpis["uncollected_volume_m3"] == pytest.approx(100.0)
    assert kpis["total_potential_generated_m3"] == pytest.approx(200.0)
