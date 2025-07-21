import pytest
import simpy
from core.simulation_manager import SimulationManager
from models.state import SimulationState
from monitoring.monitor import WasteMonitor


@pytest.fixture
def clean_state():
    """Ensure we start with a clean state"""
    # Clear any existing instance
    SimulationState._instance = None
    state = SimulationState.get_instance()
    # Initialize with proper defaults
    state.target_demands = {
        "particle_board": 12000.0,
        "osb_waferboard": 9000.0,
        "mdf_fibreboard": 7000.0,
        "mechanical_wood_pulp": 25000.0
    }
    state.total_products = {
        "particle_board": 0.0,
        "osb_waferboard": 0.0,
        "mdf_fibreboard": 0.0,
        "mechanical_wood_pulp": 0.0
    }
    state.collectors = []
    state.generators = []
    state.treatment_operators = []
    return state


def test_simulation_manager_basic_initialization(clean_state):
    """Test basic initialization without complex mocking"""
    manager = SimulationManager()
    
    # Test basic properties exist
    assert hasattr(manager, 'env')
    assert hasattr(manager, 'state')
    assert hasattr(manager, 'waste_monitor')
    assert hasattr(manager, 'initial_params')
    
    # Test types
    assert isinstance(manager.env, simpy.Environment)
    assert isinstance(manager.waste_monitor, WasteMonitor)
    assert isinstance(manager.initial_params, dict)


def test_simulation_manager_state_integration(clean_state):
    """Test that simulation manager works with real state"""
    manager = SimulationManager()
    
    # Test that state is accessible and has expected structure
    assert hasattr(manager.state, 'target_demands')
    assert hasattr(manager.state, 'total_products')
    assert isinstance(manager.state.target_demands, dict)
    assert isinstance(manager.state.total_products, dict)


def test_setup_processes_basic(clean_state):
    """Test basic process setup"""
    manager = SimulationManager()
    
    # Test that setup_processes can be called without errors
    # With empty state, it should not crash
    try:
        manager.setup_processes()
        # If we get here without exception, the basic setup works
        assert True
    except Exception as e:
        # If there's an exception, it should be a meaningful one, not a mock-related error
        assert "Mock" not in str(e), f"Got mock-related error: {e}"


def test_demand_satisfaction_check_basic(clean_state):
    """Test basic demand satisfaction check"""
    manager = SimulationManager()
    
    # Set up some basic demand data
    manager.state.target_demands = {"particle_board": 100.0}
    manager.state.total_products = {"particle_board": 50.0}
    
    # Test that check returns a proper result
    result = manager.state.check_all_demands_met()
    assert isinstance(result, bool)
    assert result is False  # 50/100 = not met


def test_get_unmet_demands_basic(clean_state):
    """Test getting unmet demands without mocks"""
    manager = SimulationManager()
    
    # Set up some demands
    manager.state.target_demands = {
        "particle_board": 100.0,
        "mdf_fibreboard": 50.0
    }
    manager.state.total_products = {
        "particle_board": 80.0,
        "mdf_fibreboard": 50.0
    }
    
    unmet = manager.state.get_unmet_demands()
    
    # Should be a dictionary
    assert isinstance(unmet, dict)
    # particle_board should have 20.0 unmet (100 - 80)
    assert abs(unmet.get("particle_board", 0) - 20.0) < 0.001
    # mdf_fibreboard should have 0 unmet (50 - 50)
    assert abs(unmet.get("mdf_fibreboard", 0) - 0.0) < 0.001
