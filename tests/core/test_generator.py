import pytest
from core.generator import WasteGenerator
from models.enums import WasteType, RegionType
from models.data_classes import WasteStream
import simpy

@pytest.fixture
def env():
    return simpy.Environment()

@pytest.fixture
def basic_generator(env):
    waste_streams = {
        WasteType.CONSTRUCTION_WOOD: 10.0,
        WasteType.SAWDUST: 5.0
    }
    return WasteGenerator(
        env=env,
        name="TestGenerator",
        waste_streams=waste_streams,
        generation_frequency=1.0,
        storage_capacity=100.0,
        priority_level=1,
        environmental_impact=1.0,
        region="GORENJSKA"
    )

def test_generator_initialization(basic_generator):
    """Test generator initialization with basic parameters"""
    assert basic_generator.name == "TestGenerator"
    assert basic_generator.storage_capacity == 100.0
    assert basic_generator.current_storage == 0.0
    assert len(basic_generator.waste_streams) == 2
    assert basic_generator.region == "GORENJSKA"
    assert basic_generator.region_type == RegionType.GORENJSKA

def test_generator_waste_generation(env, basic_generator):
    """Test waste generation over time"""
    initial_storage = basic_generator.current_storage
    
    # Run for 5 time units
    env.run(until=5)
    
    # Check if waste was generated
    assert basic_generator.current_storage > initial_storage
    assert all(stream.volume >= 0 for stream in basic_generator.waste_streams.values())
    
def test_generator_capacity_constraints(env, basic_generator):
    """Test that generator respects storage capacity constraints"""
    # Run for longer period to potentially fill storage
    env.run(until=20)
    
    # Check that storage never exceeds capacity
    assert basic_generator.current_storage <= basic_generator.storage_capacity
    total_volume = sum(stream.volume for stream in basic_generator.waste_streams.values())
    assert total_volume == basic_generator.current_storage

def test_generator_with_initial_stock():
    """Test generator initialization with initial stock"""
    env = simpy.Environment()
    initial_stock = {
        WasteType.CONSTRUCTION_WOOD: 20.0,
        WasteType.SAWDUST: 10.0
    }
    
    generator = WasteGenerator(
        env=env,
        name="TestGenerator",
        waste_streams={WasteType.CONSTRUCTION_WOOD: 10.0, WasteType.SAWDUST: 5.0},
        generation_frequency=1.0,
        storage_capacity=100.0,
        priority_level=1,
        environmental_impact=1.0,
        region="GORENJSKA",
        initial_stock=initial_stock
    )
    
    assert generator.current_storage == 30.0
    assert generator.waste_streams[WasteType.CONSTRUCTION_WOOD].volume == 20.0
    assert generator.waste_streams[WasteType.SAWDUST].volume == 10.0

def test_generator_priority_adjustment(basic_generator):
    """Test priority level adjustments based on storage"""
    initial_priority = basic_generator.priority_level
    
    # Simulate storage filling up
    for waste_type in basic_generator.waste_streams:
        basic_generator.waste_streams[waste_type].volume = basic_generator.storage_capacity * 0.8
    basic_generator.current_storage = basic_generator.storage_capacity * 0.8
    
    # Adjust priority based on high storage
    basic_generator.adjust_priority()
    assert basic_generator.priority_level > initial_priority

def test_invalid_initial_stock():
    """Test that generator raises error for invalid initial stock"""
    env = simpy.Environment()
    initial_stock = {
        WasteType.CONSTRUCTION_WOOD: 80.0,
        WasteType.SAWDUST: 30.0
    }
    
    with pytest.raises(ValueError):
        WasteGenerator(
            env=env,
            name="TestGenerator",
            waste_streams={WasteType.CONSTRUCTION_WOOD: 10.0, WasteType.SAWDUST: 5.0},
            generation_frequency=1.0,
            storage_capacity=100.0,  # Initial stock (110) exceeds this
            priority_level=1,
            environmental_impact=1.0,
            region="GORENJSKA",
            initial_stock=initial_stock
        )
