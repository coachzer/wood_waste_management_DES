import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
import simpy
from unittest.mock import Mock
from models.enums import RegionType, EntityStatus, WasteType
from models.state import SimulationState
from models.data_classes import Vehicle, CollectionCenter, WasteStream
from core.collector import CollectorCompany
from core.generator import WasteGenerator

@pytest.fixture
def env():
    """Create SimPy environment"""
    return simpy.Environment()

@pytest.fixture
def simulation_state():
    """Create a real simulation state"""
    return SimulationState()

@pytest.fixture
def collector(env):
    """Create a real collector"""
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
def generator(env):
    """Create a generator with waste"""
    from monitoring.data_collector import DataCollector
    
    # Initialize with waste already in storage
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    initial_stock = {waste_type.value: 50.0}
    
    # Initialize generator with correct waste stream format
    return WasteGenerator(
        env=env,
        name="TestGenerator",
        storage_capacity=100.0,
        waste_streams={
            waste_type.value: 50.0  # Base generation rate
        },
        generation_frequency=24,
        environmental_impact=5.0,
        region="GORENJSKA",
        data_collector=DataCollector(),
        initial_stock=initial_stock,
        uncertainty_set=None
    )

def test_initialization(collector):
    """Test collector initialization"""
    assert collector.name == "TestCollector"
    assert collector.collection_capacity == 100.0
    assert collector.collection_frequency == 24
    assert collector.transport_cost == 10.0
    assert collector.efficiency == 0.9
    assert collector.region == "GORENJSKA"
    assert collector.region_type == RegionType.GORENJSKA
    assert len(collector.vehicles) == 2
    assert isinstance(collector.collection_center, CollectionCenter)
    assert collector.status == EntityStatus.OPERATIONAL

def test_vehicle_initialization(collector):
    """Test vehicle fleet initialization"""
    assert len(collector.vehicles) == 2
    for vehicle in collector.vehicles:
        assert isinstance(vehicle, Vehicle)
        assert vehicle.capacity == 100.0  # Same as collector capacity
        assert vehicle.current_region == RegionType.GORENJSKA
        assert not vehicle.in_transit

def test_schedule_transport(collector):
    """Test waste transport scheduling"""
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    collector.collection_center.current_storage[waste_type] = 50.0
    
    success = collector.schedule_transport(
        waste_type,
        20.0,
        RegionType.GORISKA
    )
    
    assert success
    assert len(collector.active_transports) == 1
    assert collector.collection_center.current_storage[waste_type] == 30.0
    transport = collector.active_transports[0]
    assert transport["waste_type"] == waste_type
    assert transport["volume"] == 20.0

def test_collect_from_generator(collector, generator, simulation_state):
    """Test waste collection from a generator"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = [collector]
    simulation_state.generators = [generator]
    
    # Set up waste in the generator
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    generator.waste_streams[waste_type.value] = WasteStream(
        waste_type=waste_type.value,
        volume=50.0
    )
    
    # Try collection
    cost = collector.collect_from_generator(generator)
    
    assert cost > 0
    assert collector.collection_center.current_storage[waste_type] > 0

def test_collaborative_collection(collector, generator, simulation_state):
    """Test collaborative collection strategy"""
    SimulationState._instance = simulation_state
    collector.strategy = "collaborative"
    
    # Create a second collector for collaboration
    second_collector = CollectorCompany(
        env=collector.env,
        name="SecondCollector",
        collection_capacity=80.0,
        collection_frequency=24,
        transport_cost=8.0,
        environmental_impact=4.0,
        efficiency=0.8,
        region="GORENJSKA",
        num_vehicles=1
    )
    
    simulation_state.collectors = [collector, second_collector]
    simulation_state.generators = [generator]
    
    # Set up waste in the generator with proper initialization
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    generator.waste_streams = {
        waste_type.value: WasteStream(
            waste_type=waste_type.value,
            volume=50.0
        )
    }
    generator.current_storage = 50.0
    generator.region = "GORENJSKA"
    generator.region_type = RegionType.GORENJSKA
    generator.availability = True
    generator.status = EntityStatus.OPERATIONAL
    generator.mark_collected = Mock()
    
    # Run collection process for both collectors
    collector.env.process(collector.collect_waste())
    collector.env.process(second_collector.collect_waste())
    collector.env.run(until=48)  # Run for 2 full collection cycles
    
    # Verify waste was collected by either collector
    collected_main = collector.collection_center.current_storage[waste_type]
    collected_second = second_collector.collection_center.current_storage[waste_type]
    total_collected = collected_main + collected_second
    assert total_collected > 0, f"Expected total collected waste > 0, got {total_collected} (main: {collected_main}, second: {collected_second})"

def test_kanban_collection(collector, generator, simulation_state, env):
    """Test collection based on Kanban signals"""
    SimulationState._instance = simulation_state
    simulation_state.collectors = [collector]
    simulation_state.generators = [generator]
    
    # Set up waste in the generator
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01
    generator.waste_streams = {
        waste_type.value: WasteStream(
            waste_type=waste_type.value,
            volume=50.0
        )
    }
    generator.current_storage = 50.0
    
    # Add a Kanban signal with proper waste type format
    collector.kanban_manager.add_signal(
        'CONSTRUCTION_WOOD_17_02_01',  # Just the waste type string
        priority=1, 
        timestamp=env.now
    )
    
    # Run collection process for multiple cycles
    collector.env.process(collector.collect_waste())
    collector.env.run(until=48)  # Run for 2 full collection cycles
    
    # Verify Kanban signal was processed
    collected = collector.collection_center.current_storage[waste_type]
    assert collected > 0, f"Expected collected waste from Kanban > 0, got {collected}"
    assert collector.kanban_manager.get_signals() == [], "Kanban signals should be cleared"

def test_failure_handling(collector):
    """Test collector failure handling"""
    # Set up failure state
    collector.status = EntityStatus.FAILED
    collector.failure_time = 0
    collector.recovery_time = 100
    
    # Check during failure
    assert collector._check_failure_and_recovery(50)
    assert collector.status == EntityStatus.FAILED
    
    # Check recovery
    assert not collector._check_failure_and_recovery(101)
    assert collector.status == EntityStatus.OPERATIONAL
