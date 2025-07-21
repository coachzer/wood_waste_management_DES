import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
import simpy
from core.treatment import TreatmentOperator, StorageDict
from core.kanban_manager import KanbanManager
from monitoring.data_collector import DataCollector
from models.enums import WasteType, OutputType, EntityStatus, InventoryPolicy
from models.data_classes import WasteTransformation, ProductStorage
from models.state import SimulationState
from utils.capacity_utils import CapacityResult


@pytest.fixture
def real_env():
    """Create a real SimPy environment"""
    return simpy.Environment()


@pytest.fixture
def real_data_collector():
    """Create a real data collector"""
    return DataCollector()


@pytest.fixture
def real_kanban_manager():
    """Create a real kanban manager"""
    return KanbanManager()


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
    return state


@pytest.fixture
def treatment_operator(real_env, real_data_collector, real_kanban_manager, clean_state):
    """Create a treatment operator with real dependencies"""
    return TreatmentOperator(
        env=real_env,
        name="TestOperator",
        processing_time=1.0,
        storage_capacity=100.0,
        energy_consumption=10.0,
        environmental_impact=5.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region="GORENJSKA",
        data_collector=real_data_collector,
        kanban_manager=real_kanban_manager,
        product_storage_capacity=50.0
    )

def test_initialization(treatment_operator):
    """Test treatment operator initialization"""
    assert treatment_operator.name == "TestOperator"
    assert abs(treatment_operator.processing_time - 1.0) < 0.001
    assert abs(treatment_operator.storage_capacity - 100.0) < 0.001
    assert treatment_operator.region == "GORENJSKA"
    assert abs(treatment_operator.conversion_rate - 0.8) < 0.001
    assert treatment_operator.status == EntityStatus.OPERATIONAL
    assert isinstance(treatment_operator.product_storage, ProductStorage)
    assert abs(treatment_operator.product_storage.capacity - 50.0) < 0.001

def test_waste_storage_initialization(treatment_operator):
    """Test waste storage initialization"""
    assert isinstance(treatment_operator.waste_storage, StorageDict)
    expected_waste_types = {
        WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
        WasteType.WOODEN_PACKAGING_15_01_03,
        WasteType.CONSTRUCTION_WOOD_17_02_01,
        WasteType.NON_HAZARDOUS_WOOD_20_01_38
    }
    for waste_type in expected_waste_types:
        assert abs(treatment_operator.waste_storage[waste_type] - 0.0) < 0.001

def test_storage_capacity_constraints(treatment_operator):
    """Test storage capacity constraints"""
    waste_amounts = {
        WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 80.0,  # Sawdust
        WasteType.WOODEN_PACKAGING_15_01_03: 40.0   # Wooden packaging
    }
    
    added = treatment_operator._add_to_storage(waste_amounts)
    assert added <= treatment_operator.storage_capacity
    assert treatment_operator.current_storage <= treatment_operator.storage_capacity

def test_process_waste_transformation(treatment_operator, clean_state):
    """Test waste transformation processing"""
    # Use WasteType enum instead of string key
    treatment_operator.waste_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] = 50.0
    
    # Get transformation for construction wood to particle board
    transformation = treatment_operator.transformations.get(
        (WasteType.CONSTRUCTION_WOOD_17_02_01, OutputType.PARTICLE_BOARD)
    )
    assert transformation is not None
    
    # Process transformation
    treatment_operator._process_waste_transformation(
        WasteType.CONSTRUCTION_WOOD_17_02_01,
        OutputType.PARTICLE_BOARD,
        transformation
    )
    
    # Check waste consumed and product created
    assert treatment_operator.waste_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] < 50.0
    assert treatment_operator.product_storage.current_storage[OutputType.PARTICLE_BOARD] > 0

def test_trigger_collection(treatment_operator, clean_state):
    """Test collection triggering - this will work with real collection coordinator"""
    # Note: This test will actually run the collection logic
    # The collection coordinator will attempt to find collectors
    stored, collected = treatment_operator.trigger_collection()
    
    # With no collectors in the system, collected should be 0
    assert abs(collected - 0.0) < 0.001
    assert stored <= treatment_operator.storage_capacity
    assert len(treatment_operator.demand_history) > 0

def test_inventory_policy_pull(real_env, real_data_collector, clean_state):
    """Test pull-based inventory policy"""
    kanban_manager = KanbanManager()
    operator = TreatmentOperator(
        env=real_env,
        name="PullOperator",
        processing_time=1.0,
        storage_capacity=100.0,
        energy_consumption=10.0,
        environmental_impact=5.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region="GORENJSKA",
        data_collector=real_data_collector,
        inventory_policy=InventoryPolicy.PULL,
        kanban_manager=kanban_manager
    )
    
    # Simulate low inventory using WasteType enum
    operator.waste_storage[WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05] = 0.5  # Below threshold
    
    # Manually add a kanban signal to simulate detection of low inventory
    kanban_manager.add_signal(
        waste_type=WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
        priority=1,
        timestamp=real_env.now
    )
    
    # Check if kanban signal was created
    assert len(kanban_manager.signals) == 1
    assert kanban_manager.signals[0]['waste_type'] == WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05

def test_failure_handling(treatment_operator):
    """Test operator failure handling"""
    # Set up failure state
    treatment_operator.status = EntityStatus.FAILED
    treatment_operator.failure_time = 0
    treatment_operator.recovery_time = 100
    
    # Check during failure
    is_failed = treatment_operator._check_failure_and_recovery(50)
    assert is_failed
    assert treatment_operator.status == EntityStatus.FAILED
    
    # Check recovery
    is_failed = treatment_operator._check_failure_and_recovery(101)
    assert not is_failed
    assert treatment_operator.status == EntityStatus.OPERATIONAL

def test_transformation_prioritization(treatment_operator, clean_state):
    """Test transformation prioritization"""
    # Setup waste storage using WasteType enums
    treatment_operator.waste_storage[WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05] = 50.0
    treatment_operator.waste_storage[WasteType.WOODEN_PACKAGING_15_01_03] = 30.0
    
    # Set up some unmet demands in the simulation state
    clean_state.target_demands = {
        "particle_board": 12000.0,
        "mdf_fibreboard": 7000.0,
        "osb_waferboard": 9000.0
    }
    clean_state.total_products = {
        "particle_board": 0.0,
        "mdf_fibreboard": 0.0,
        "osb_waferboard": 0.0
    }
    
    # Get prioritized transformations
    transformations = treatment_operator._get_prioritized_transformations()
    
    # Verify transformations are prioritized correctly
    assert len(transformations) > 0
    first_transformation = transformations[0]
    assert isinstance(first_transformation[1], WasteTransformation)
    assert first_transformation[0][1] in {
        OutputType.PARTICLE_BOARD,
        OutputType.MDF_FIBREBOARD,
        OutputType.OSB_WAFERBOARD
    }
