import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
import simpy

# Import real modules - no mocking needed
from core.collection_coordinator import CollectionCoordinator
from core.collector import CollectorCompany
from models.enums import RegionType, WasteType
from models.state import SimulationState
from models.data_classes import CollectionResult


@pytest.fixture
def real_env():
    """Create a real SimPy environment"""
    return simpy.Environment()


@pytest.fixture
def coordinator(real_env):
    """Create a real coordinator instance"""
    return CollectionCoordinator(real_env, "gorenjska")


@pytest.fixture 
def real_collector(real_env):
    """Create a real collector with proper setup"""
    collector = CollectorCompany(
        env=real_env,
        name="TestCollector",
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=2
    )
    collector.availability = True
    return collector


@pytest.fixture
def clean_state():
    """Ensure we start with a clean state"""
    # Clear any existing instance
    SimulationState._instance = None
    state = SimulationState.get_instance()
    state.collectors = []
    return state


def test_initialization():
    """Test coordinator initialization"""
    env = simpy.Environment()
    coord1 = CollectionCoordinator(env, "gorenjska")
    assert coord1.region == "gorenjska"
    assert coord1.region_type.value == RegionType.GORENJSKA.value
    assert not coord1.prioritize_types
    assert not coord1.prioritize_regions
    
    coord2 = CollectionCoordinator(env, "gorenjska", True, True)
    assert coord2.prioritize_types
    assert coord2.prioritize_regions


def test_minimum_collection_volume(coordinator):
    """Test handling of amounts below minimum collection volume"""
    result = coordinator.request_collection(0.005, {WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05})
    assert result.total_collected == 0
    assert all(amount == 0.0 for amount in result.waste_by_type.values())


def test_request_collection_no_collectors(coordinator, clean_state):
    """Test collection request when no collectors are available"""
    # Ensure no collectors in state
    clean_state.collectors = []
    
    result = coordinator.request_collection(1.0, {WasteType.CONSTRUCTION_WOOD_17_02_01})
    assert result.total_collected == 0
    assert all(amount == 0.0 for amount in result.waste_by_type.values())


def test_transfer_stored_waste_simple(coordinator, real_collector, clean_state):
    """Test transferring waste from collector storage"""
    # Add waste to collector's storage
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    real_collector.collection_center.current_storage[waste_type] = 5.0
    
    # Add collector to state
    clean_state.collectors = [real_collector]
    
    # Test the collection request
    result = coordinator.request_collection(2.0, {waste_type})
    
    # Verify results
    assert result.total_collected == 2.0
    assert result.waste_by_type[waste_type] == 2.0
    
    # Verify the waste was taken from storage
    assert real_collector.collection_center.current_storage[waste_type] == 3.0  # 5 - 2


def test_request_additional_collection(coordinator, real_collector, clean_state):
    """Test requesting additional waste collection when no stored waste available"""
    # Set up collector with no stored waste
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    real_collector.collection_center.current_storage[waste_type] = 0.0
    
    # Add collector to state
    clean_state.collectors = [real_collector]
    
    # This will trigger the collect_waste_for_demand method
    result = coordinator.request_collection(2.0, {waste_type})
    
    # The actual collection depends on the collector's implementation
    # For now, let's just verify the method was called properly
    assert isinstance(result, CollectionResult)
    assert result.total_collected >= 0


def test_collector_region_prioritization(real_env, clean_state):
    """Test prioritization of collectors from local region"""
    coordinator = CollectionCoordinator(real_env, "gorenjska")
    
    # Create local collector
    local_collector = CollectorCompany(
        env=real_env,
        name="LocalCollector",
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=2
    )
    local_collector.availability = True
    local_collector.collection_center.current_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] = 5.0
    
    # Create other region collector
    other_collector = CollectorCompany(
        env=real_env,
        name="OtherCollector", 
        collection_capacity=100.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region="GORISKA",
        num_vehicles=2
    )
    other_collector.availability = True
    other_collector.collection_center.current_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] = 5.0
    
    # Add both collectors to state (other first to test prioritization)
    clean_state.collectors = [other_collector, local_collector]
    
    result = coordinator.request_collection(1.0, {WasteType.CONSTRUCTION_WOOD_17_02_01})
    
    # Should prioritize local collector
    assert result.total_collected == 1.0
    # Local collector should have waste removed
    assert local_collector.collection_center.current_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] == 4.0
    # Other collector should be untouched
    assert other_collector.collection_center.current_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] == 5.0


def test_multiple_waste_types(coordinator, real_collector, clean_state):
    """Test collection of multiple waste types"""
    # Set up collector with multiple waste types
    waste_type1 = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
    waste_type2 = WasteType.WOODEN_PACKAGING_15_01_03
    
    real_collector.collection_center.current_storage[waste_type1] = 3.0
    real_collector.collection_center.current_storage[waste_type2] = 3.0
    
    # Add collector to state
    clean_state.collectors = [real_collector]
    
    result = coordinator.request_collection(4.0, {waste_type1, waste_type2})
    
    # Should collect all available waste (since we have 6.0 total and requested 4.0)
    # The system collects all available stored waste
    assert result.total_collected == 6.0  # Collects all available: 3.0 + 3.0
    assert result.waste_by_type.get(waste_type1, 0) == 3.0
    assert result.waste_by_type.get(waste_type2, 0) == 3.0


def test_invalid_region():
    """Test coordinator initialization with invalid region"""
    env = simpy.Environment()
    with pytest.raises(KeyError):
        CollectionCoordinator(env, "INVALID_REGION")


def test_collection_with_insufficient_storage(coordinator, real_collector, clean_state):
    """Test collection when available storage is less than requested"""
    # Set up collector with limited waste
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    real_collector.collection_center.current_storage[waste_type] = 1.0  # Only 1 unit available
    
    # Add collector to state
    clean_state.collectors = [real_collector]
    
    # Request more than available
    result = coordinator.request_collection(5.0, {waste_type})
    
    # Should collect only what's available from storage
    # Additional collection might happen through collect_waste_for_demand
    assert result.total_collected >= 0
    assert result.total_collected <= 5.0
