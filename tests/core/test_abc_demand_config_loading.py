"""The ABC demand config must fail loudly when missing (cleanup item 62).

Both fallback layers used to swallow a bad path -- the analyzer substituted
hardcoded national demand on FileNotFoundError, and the treatment initializer
substituted hardcoded priority weights on any exception -- so a moved or
renamed demand.json silently changed what every operator produces while
looking like a configured run. These tests pin the new contract: a missing
file raises, and the real file still classifies.
"""

import pytest

from core.abc_analysis import BiogenicCarbonABCAnalyzer


def test_missing_demand_config_raises():
    with pytest.raises(FileNotFoundError):
        BiogenicCarbonABCAnalyzer("data/nonexistent_demand.json")


def test_real_demand_config_classifies_all_products():
    """Non-vacuity: the shipped config loads and yields a weight per product."""
    analyzer = BiogenicCarbonABCAnalyzer("data/demand.json")
    classifications = analyzer.perform_abc_classification()

    priority_map = {item.product_type: item.priority_weight for item in classifications}
    assert set(priority_map) == {"mdf", "particle_board", "osb"}
    assert all(weight > 0 for weight in priority_map.values())
