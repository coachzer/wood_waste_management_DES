import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
from unittest.mock import Mock
from models.enums import RegionType, WasteType
from models.state import SimulationState
from models.data_classes import CollectionCenter
from core.collection_coordinator import CollectionCoordinator
from core.collector import CollectorCompany

@pytest.fixture
def env():
    """Simple environment that tracks time"""
    class SimpleEnv:
        def __init__(self):
            self.now = 0
            
        def process(self, gen):
            return gen
            
        def run(self):
            self.now += 1
            
    return SimpleEnv()

@pytest.fixture
def simulation_state():
    """Create a real simulation state"""
    return SimulationState()

@pytest.fixture
def collector(env):
    """Create a real collector with collection center"""
    return CollectorCompany(
        env=env,
        name="TestCollector",
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=2
    )

@pytest.fixture
def coordinator(env):
    """Create a coordinator"""
    return CollectionCoordinator(env, "gorenjska")

def test_initialization(env):
    """Test coordinator initialization with real objects"""
    coordinator = CollectionCoordinator(env, "gorenjska")
    assert coordinator.region == "gorenjska"
    assert coordinator.region_type == RegionType.GORENJSKA
    assert not coordinator.prioritize_types
    assert not coordinator.prioritize_regions

def test_minimum_collection_volume(coordinator):
    """Test minimum collection volume check"""
    result = coordinator.request_collection(0.005, {WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05})
    assert result.total_collected == 0
    assert result.waste_by_type.get(WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05, 0.0) == 0.0

def test_request_collection_no_collectors(coordinator, simulation_state):
    """Test collection request with no collectors available"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = []
    
    result = coordinator.request_collection(1.0, {WasteType.CONSTRUCTION_WOOD_17_02_01})
    assert result.total_collected == 0
    assert result.waste_by_type.get(WasteType.CONSTRUCTION_WOOD_17_02_01, 0.0) == 0.0

def test_transfer_stored_waste(coordinator, simulation_state, collector):
    """Test transferring waste from collector storage"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = [collector]
    
    # Add some waste to collector's storage
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    collector.collection_center.current_storage[waste_type] = 5.0
    
    result = coordinator.request_collection(2.0, {waste_type})
    
    assert result.total_collected == 2.0
    assert result.waste_by_type[waste_type] == 2.0
    assert collector.collection_center.current_storage[waste_type] == 3.0

def test_request_additional_collection(coordinator, simulation_state, collector):
    """Test requesting additional waste collection"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = [collector]
    
    # Prepare collector's collection center
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    
    # Add some waste directly to collector's storage to simulate collected waste
    collector.collection_center.current_storage[waste_type] = 5.0  # Start with some waste
    collector.collection_center.storage_capacity = 100.0
    
    # Run collection request
    result = coordinator.request_collection(2.0, {waste_type})
    
    # Verify collection worked
    assert result.total_collected == 2.0
    assert result.waste_by_type[waste_type] == 2.0
    # Verify remaining storage
    assert collector.collection_center.current_storage[waste_type] == 3.0

def test_collector_region_prioritization(coordinator, simulation_state, env):
    """Test prioritization of collectors from local region"""
    SimulationState._instance = simulation_state
    
    # Create collectors from different regions
    local_collector = CollectorCompany(
        env=env,
        name="LocalCollector",
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=2
    )
    
    other_collector = CollectorCompany(
        env=env,
        name="OtherCollector",
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORISKA",
        num_vehicles=2
    )
    
    simulation_state.collectors = [other_collector, local_collector]
    
    # Add waste to both collectors
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    local_collector.collection_center.current_storage[waste_type] = 2.0
    other_collector.collection_center.current_storage[waste_type] = 2.0
    
    result = coordinator.request_collection(1.0, {waste_type})
    
    assert result.total_collected == 1.0
    # Verify local collector's storage was used first
    assert local_collector.collection_center.current_storage[waste_type] == 1.0
    assert other_collector.collection_center.current_storage[waste_type] == 2.0

def test_invalid_region(env):
    """Test coordinator initialization with invalid region"""
    with pytest.raises(KeyError):
        CollectionCoordinator(env, "INVALID_REGION")

def test_multiple_waste_types(coordinator, simulation_state, collector):
    """Test collection of multiple waste types"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = [collector]
    
    # Set up multiple waste types
    collector.collection_center.current_storage[WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05] = 2.0
    collector.collection_center.current_storage[WasteType.WOODEN_PACKAGING_15_01_03] = 2.0
    
    result = coordinator.request_collection(
        4.0, 
        {WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05, WasteType.WOODEN_PACKAGING_15_01_03}
    )
    
    # Should collect from both waste types
    assert result.total_collected == 4.0
    assert result.waste_by_type[WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05] == 2.0
    assert result.waste_by_type[WasteType.WOODEN_PACKAGING_15_01_03] == 2.0
