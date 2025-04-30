import pytest
import simpy
from core.treatment import TreatmentOperator
from models.enums import WasteType, OutputType, RegionType
from models.data_classes import WasteTransformation
from models.state import SimulationState
from monitoring.data_collector import DataCollector

@pytest.fixture
def env():
    return simpy.Environment()

@pytest.fixture
def data_collector(env):
    return DataCollector(env)

@pytest.fixture
def simulation_state():
    state = SimulationState.get_instance()
    state.reset()
    return state

@pytest.fixture
def basic_treatment(env, data_collector):
    """Create a basic treatment operator for testing"""
    return TreatmentOperator(
        env=env,
        name="TestTreatment",
        processing_time=1.0,
        storage_capacity=300.0,
        energy_consumption=50.0,
        environmental_impact=1.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region="GORENJSKA",
        data_collector=data_collector
    )

def test_treatment_initialization(basic_treatment):
    """Test treatment operator initialization"""
    assert basic_treatment.name == "TestTreatment"
    assert basic_treatment.storage_capacity == 300.0
    assert basic_treatment.region == "GORENJSKA"
    assert basic_treatment.region_type == RegionType.GORENJSKA
    assert basic_treatment.processing_capacity > 0
    assert basic_treatment.conversion_rate == 0.8

def test_waste_storage_management(basic_treatment):
    """Test waste storage operations"""
    waste_type = WasteType.CONSTRUCTION_WOOD
    
    # Add waste to storage
    basic_treatment.waste_storage[waste_type] = 50.0
    assert basic_treatment.waste_storage[waste_type] == 50.0
    assert basic_treatment.current_storage == 50.0
    
    # Verify storage constraints
    excess_amount = basic_treatment.storage_capacity + 10.0
    basic_treatment.waste_storage[waste_type] = excess_amount
    assert basic_treatment.current_storage <= basic_treatment.storage_capacity

def test_waste_transformation(env, basic_treatment, simulation_state):
    """Test waste transformation process"""
    # Add waste to storage
    waste_type = WasteType.CONSTRUCTION_WOOD
    basic_treatment.waste_storage[waste_type] = 100.0
    
    # Set up demand in simulation state
    simulation_state.target_demands = {
        'wooden_furniture': 50.0,
        'wooden_packaging': 30.0,
        'paper_packaging': 20.0
    }
    
    # Run simulation for processing period
    env.run(until=5)
    
    # Verify processing occurred
    assert basic_treatment.processed_volumes[waste_type] > 0
    assert basic_treatment.waste_storage[waste_type] < 100.0
    assert any(volume > 0 for volume in basic_treatment.product_volumes.values())

def test_demand_based_collection(env, basic_treatment, simulation_state):
    """Test collection triggering based on demand"""
    # Set initial demand
    simulation_state.target_demands = {
        'wooden_furniture': 100.0,
        'wooden_packaging': 50.0,
        'paper_packaging': 30.0
    }
    
    # Trigger collection
    stored, collected = basic_treatment.trigger_collection()
    
    # Verify collection request was processed
    assert stored >= 0
    assert collected >= 0
    assert basic_treatment.current_storage <= basic_treatment.storage_capacity

def test_transformation_efficiency(env, basic_treatment):
    """Test transformation efficiency calculations"""
    waste_type = WasteType.CONSTRUCTION_WOOD
    input_amount = 100.0
    basic_treatment.waste_storage[waste_type] = input_amount
    
    # Process waste
    transformation = basic_treatment.transformations[(waste_type, OutputType.WOODEN_FURNITURE)]
    efficiency = basic_treatment.transformation_efficiency
    
    expected_output = input_amount * efficiency * transformation.conversion_efficiency
    
    # Run simulation
    env.run(until=2)
    
    # Verify efficiency was applied
    assert basic_treatment.product_volumes['wooden_furniture'] > 0
    assert basic_treatment.product_volumes['wooden_furniture'] <= expected_output

def test_capacity_management(basic_treatment):
    """Test dynamic capacity management"""
    initial_capacity = basic_treatment.storage_capacity
    
    # Simulate high utilization
    for waste_type in WasteType:
        basic_treatment.waste_storage[waste_type] = basic_treatment.storage_capacity / len(WasteType)
    
    # Verify capacity constraints
    assert basic_treatment.current_storage <= basic_treatment.max_capacity
    assert basic_treatment.current_storage >= basic_treatment.min_capacity

def test_multiple_waste_processing(env, basic_treatment, simulation_state):
    """Test processing multiple waste types simultaneously"""
    # Add different types of waste
    basic_treatment.waste_storage[WasteType.CONSTRUCTION_WOOD] = 50.0
    basic_treatment.waste_storage[WasteType.SAWDUST] = 30.0
    basic_treatment.waste_storage[WasteType.WASTE_WOODEN_PACKAGING] = 20.0
    
    initial_total = basic_treatment.current_storage
    
    # Set demands
    simulation_state.target_demands = {
        'wooden_furniture': 40.0,
        'wooden_packaging': 30.0,
        'paper_packaging': 20.0
    }
    
    # Run processing
    env.run(until=5)
    
    # Verify multiple waste types were processed
    assert basic_treatment.current_storage < initial_total
    assert sum(basic_treatment.product_volumes.values()) > 0
    assert basic_treatment.processed_volumes[WasteType.CONSTRUCTION_WOOD] > 0
    assert basic_treatment.processed_volumes[WasteType.SAWDUST] > 0

def test_prioritized_processing(env, basic_treatment, simulation_state):
    """Test that processing prioritizes based on demand"""
    # Add waste
    basic_treatment.waste_storage[WasteType.CONSTRUCTION_WOOD] = 100.0
    
    # Set specific demand
    simulation_state.target_demands = {
        'wooden_furniture': 80.0,  # High demand
        'wooden_packaging': 20.0,  # Low demand
        'paper_packaging': 0.0     # No demand
    }
    
    # Run processing
    env.run(until=5)
    
    # Verify prioritization
    assert basic_treatment.product_volumes['wooden_furniture'] > basic_treatment.product_volumes['wooden_packaging']
    assert basic_treatment.product_volumes['paper_packaging'] == 0.0
