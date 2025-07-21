import pytest
import simpy
from unittest.mock import Mock
from core.simulation_manager import SimulationManager
from models.state import SimulationState
from monitoring.monitor import WasteMonitor

class ProcessMock:
    """Mock for SimPy processes that provides iteration support"""
    def __init__(self, generator):
        self.generator = generator
        
    def __iter__(self):
        return self
        
    def __next__(self):
        try:
            return next(self.generator)
        except StopIteration:
            raise StopIteration

@pytest.fixture
def mock_env():
    """Mock SimPy environment"""
    env = Mock(spec=simpy.Environment)
    env.now = 0
    # Make env.process return an iterable mock
    env.process = lambda gen: ProcessMock(gen)
    return env

@pytest.fixture
def mock_state():
    """Mock simulation state"""
    state = Mock(spec=SimulationState)
    state.generators = []
    state.collectors = []
    state.treatment_operators = []
    state.total_products = {"particle_board": 50, "mdf_fibreboard": 30}
    state.target_demands = {"particle_board": 100, "mdf_fibreboard": 50}
    return state

@pytest.fixture
def simulation_manager(monkeypatch, mock_env, mock_state):
    """Setup SimulationManager with mocked dependencies"""
    monkeypatch.setattr(simpy, "Environment", Mock(return_value=mock_env))
    monkeypatch.setattr(SimulationState, "get_instance", Mock(return_value=mock_state))
    
    return SimulationManager()

def test_initialization(simulation_manager):
    """Test basic initialization of SimulationManager"""
    assert simulation_manager.env is not None
    assert isinstance(simulation_manager.waste_monitor, WasteMonitor)
    assert simulation_manager.state is not None
    assert simulation_manager.initial_params == {}

def test_initialize_entities_simple():
    """Test entity initialization with simple approach - no mocks"""
    from core.simulation_manager import SimulationManager
    from models.state import SimulationState
    
    # Clear any existing state
    SimulationState._instance = None
    
    # Create a real simulation manager
    manager = SimulationManager()
    
    # Test basic initialization
    assert hasattr(manager, 'env')
    assert hasattr(manager, 'state')
    assert hasattr(manager, 'initial_params')
    assert isinstance(manager.initial_params, dict)
    
    # Test that we can access the state
    assert manager.state is not None
    assert hasattr(manager.state, 'generators')
    assert hasattr(manager.state, 'collectors')
    assert hasattr(manager.state, 'treatment_operators')

def test_setup_processes(simulation_manager):
    """Test process setup"""
    def mock_process_gen():
        yield simulation_manager.env.timeout(1)
    
    simulation_manager.env.process = Mock(return_value=ProcessMock(mock_process_gen()))
    simulation_manager.setup_processes()
    assert simulation_manager.env.process.call_count == 2

def test_check_demand_satisfaction(simulation_manager):
    """Test demand satisfaction check"""
    simulation_manager.state.check_all_demands_met.return_value = True
    
    # Call the generator function directly to test its logic
    generator = simulation_manager._check_demand_satisfaction()
    # Advance the generator once
    next(generator, None)
    
    simulation_manager.state.check_all_demands_met.assert_called_once()

def test_run_simulation(simulation_manager):
    """Test simulation run"""
    # Set up the simulation_manager with real state that returns proper dictionaries
    simulation_manager.state.get_unmet_demands = lambda: {}  # Return empty dict instead of Mock
    simulation_manager.state.target_demands = {}
    simulation_manager.state.total_products = {}
    
    # Set up mock processes
    def mock_process_gen():
        yield simulation_manager.env.timeout(1)
    
    simulation_manager.processes = [
        ProcessMock(mock_process_gen()),
        ProcessMock(mock_process_gen())
    ]
    
    # Run simulation
    simulation_manager.run_simulation()
    
    # Verify env.run was called
    simulation_manager.env.run.assert_called_once()

def test_print_final_status_unmet_demands(simulation_manager, capsys):
    """Test final status printing with unmet demands"""
    simulation_manager.state.get_unmet_demands.return_value = {
        "particle_board": 50,
        "mdf_fibreboard": 20
    }
    
    simulation_manager._print_final_status()
    captured = capsys.readouterr()
    
    assert "Some demands were not met:" in captured.out
    assert "particle_board: 50.00/100.00" in captured.out
    assert "mdf_fibreboard: 30.00/50.00" in captured.out

def test_print_final_status_all_met(simulation_manager, capsys):
    """Test final status printing with all demands met"""
    simulation_manager.state.get_unmet_demands.return_value = {
        "particle_board": 0,
        "mdf_fibreboard": 0
    }
    
    simulation_manager._print_final_status()
    captured = capsys.readouterr()
    
    assert "All demands were successfully met!" in captured.out
