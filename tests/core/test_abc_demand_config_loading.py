"""The demand config must fail loudly when missing (cleanup item 62).

Both fallback layers used to swallow a bad path -- the analyzer substituted
hardcoded national demand on FileNotFoundError, and the treatment initializer
substituted hardcoded priority weights on any exception -- so a moved or
renamed demand.json silently changed what every operator produces while
looking like a configured run. These tests pin the contract: a missing file
raises, and the real file still classifies.
"""

import pytest

from core.abc_analysis import abc_priority_weights
from models.facility_data import FacilityDataManager


def test_missing_demand_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FacilityDataManager(data_dir=str(tmp_path)).load_data()


def test_real_demand_config_classifies_all_products():
    """Non-vacuity: the shipped config loads and yields a weight per product."""
    facility_manager = FacilityDataManager()
    facility_manager.load_data()

    priority_map = abc_priority_weights(facility_manager.demand)

    assert set(priority_map) == {"mdf", "particle_board", "osb"}
    assert all(weight > 0 for weight in priority_map.values())
