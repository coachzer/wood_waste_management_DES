import sys
import os
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from models.state import SimulationState

def test_state_initialization():
    state = SimulationState()
    assert state is not None

def test_state_has_expected_attributes():
    state = SimulationState()
    # Example: check for common attributes, adjust as needed
    assert hasattr(state, "generators")
    assert hasattr(state, "collectors")
    assert hasattr(state, "treatment_operators")
    assert hasattr(state, "total_products")
    assert hasattr(state, "target_demands")
    assert hasattr(state, "demand_met_times")

@pytest.mark.parametrize("product_type", ["mdf_fibreboard", "particle_board", "osb_waferboard"])
def test_product_tracking(product_type):
    state = SimulationState()
    state.total_products[product_type] = 0
    state.track_product_production(product_type, 10)
    assert state.total_products[product_type] == 10

def test_reset_state():
    state = SimulationState()
    state.total_products["mdf_fibreboard"] = 100
    state.reset()
    assert state.total_products["mdf_fibreboard"] == 0
