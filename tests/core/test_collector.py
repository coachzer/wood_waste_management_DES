import pytest
import simpy
from unittest.mock import Mock
from core.collector import CollectorCompany
from core.generator import WasteGenerator
from models.enums import WasteType, RegionType
from models.state import SimulationState

@pytest.fixture
def env():
    return simpy.Environment()

@pytest.fixture
def simulation_state():
    state = SimulationState.get_instance()
    state.reset()  # Ensure clean state
    return state

@pytest.fixture
def basic_collector(env):
    return CollectorCompany(
        env=env,
        name="TestCollector",
        collection_capacity=200.0,
        collection_frequency=1.0,
        transport_cost=10.0,
        environmental_impact=1.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=2,
        vehicle_capacity=100.0
    )

@pytest.fixture
def basic_generator(env):
    waste_streams = {
        WasteType.CONSTRUCTION_WOOD_17_02_01.value: 10.0,
        WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05.value: 5.0
    }
    initial_stock = {
        WasteType.CONSTRUCTION_WOOD_17_02_01.value: 50.0,
        WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05.value: 25.0
    }
    return WasteGenerator(
        env=env,
        name="TestGenerator",
        waste_streams=waste_streams,
        generation_frequency=1.0,
        storage_capacity=200.0,
        environmental_impact=1.0,
        region="GORENJSKA",
        initial_stock=initial_stock,
        data_collector=Mock()  # Use Mock instead of None
    )

def test_collector_initialization(basic_collector):
    """Test collector initialization with basic parameters"""
    assert basic_collector.name == "TestCollector"
    assert basic_collector.collection_capacity == 200.0
    assert basic_collector.region == "GORENJSKA"
    assert basic_collector.region_type == RegionType.GORENJSKA
    assert len(basic_collector.vehicles) == 2
    assert basic_collector.vehicles[0].capacity == 100.0

def test_collector_capacity_constraints(basic_collector):
    """Test that collector respects capacity constraints"""
    # Check initial state
    assert basic_collector.collection_center.storage_capacity == 400.0  # Double the collection capacity
    
    # Verify capacity constraints are enforced
    for waste_type in WasteType:
        actual_added = basic_collector.collection_center.current_storage.get(waste_type, 0.0)
        assert actual_added <= basic_collector.collection_center.storage_capacity

def test_collection_from_generator(basic_collector, basic_generator):
    """Test waste collection from a generator"""
    # Get initial states
    initial_generator_storage = basic_generator.current_storage
    initial_collector_storage = sum(basic_collector.collection_center.current_storage.values())
    
    # Perform collection
    collection_cost = basic_collector.collect_from_generator(basic_generator)
    
    # Verify collection occurred
    assert basic_generator.current_storage < initial_generator_storage
    assert sum(basic_collector.collection_center.current_storage.values()) > initial_collector_storage
    assert collection_cost > 0

def test_vehicle_management(basic_collector):
    """Test vehicle allocation and management"""
    # Initially all vehicles should be available
    available_vehicles = [v for v in basic_collector.vehicles if not v.in_transit]
    assert len(available_vehicles) == 2
    
    # Add waste to storage and schedule transport to put vehicle in transit
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    basic_collector.collection_center.current_storage[waste_type] = 60.0
    
    # Schedule transport which should put a vehicle in transit
    success = basic_collector.schedule_transport(
        waste_type,
        30.0,
        RegionType.GORISKA
    )
    
    assert success
    # Check vehicle allocation after scheduling transport
    available_vehicles = [v for v in basic_collector.vehicles if not v.in_transit]
    assert len(available_vehicles) == 1  # One vehicle should be in transit

def test_collaborative_collection(env, basic_collector, basic_generator):
    """Test collaborative collection strategy"""
    # Create another collector for collaboration
    collaborator = CollectorCompany(
        env=env,
        name="Collaborator",
        collection_capacity=150.0,
        collection_frequency=1.0,
        transport_cost=12.0,
        environmental_impact=1.0,
        efficiency=0.85,
        region="GORENJSKA",
        strategy="collaborative"
    )
    
    # Test collaborative collection
    basic_collector.strategy = "collaborative"
    basic_collector.collect_with_collaboration(basic_generator, [collaborator])
    
    # Verify waste distribution between collectors
    assert sum(basic_collector.collection_center.current_storage.values()) > 0
    assert sum(collaborator.collection_center.current_storage.values()) > 0

def test_collection_priority(env, basic_collector, basic_generator):
    """Test collection prioritization"""
    # Set high priority for generator
    basic_generator.priority_level = 8
    initial_storage = basic_generator.current_storage
    
    # Perform collection
    basic_collector.collect_from_generator(basic_generator)
    
    # Verify high-priority generator was serviced
    assert basic_generator.current_storage < initial_storage

def test_transport_scheduling(env, basic_collector):
    """Test transport scheduling and execution"""
    # Add some waste to collector's storage
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    basic_collector.collection_center.current_storage[waste_type] = 75.0
    
    # Schedule transport
    result = basic_collector.schedule_transport(
        waste_type=waste_type,
        volume=50.0,
        target_region=RegionType.GORENJSKA
    )
    
    assert result is True
    assert len(basic_collector.active_transports) == 1
    assert basic_collector.collection_center.current_storage[waste_type] == 25.0

    # Run simulation to complete transport
    env.run(until=10)
    assert len(basic_collector.active_transports) == 0
