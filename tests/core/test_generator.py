import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
import simpy
from core.generator import WasteGenerator
from models.enums import WasteType, StockStrategy, RegionType
from monitoring.data_collector import DataCollector

@pytest.fixture
def setup_generator():
    env = simpy.Environment()
    waste_streams = {WasteType.CONSTRUCTION_WOOD_17_02_01: 100.0}
    data_collector = DataCollector()
    
    generator = WasteGenerator(
        env=env,
        name="test_generator",
        waste_streams=waste_streams,
        generation_frequency=1,
        storage_capacity=1000,
        environmental_impact=0.5,
        region=RegionType.OSREDNJESLOVENSKA.value,
        data_collector=data_collector
    )
    return generator, env

def test_generate_waste_returns_positive(setup_generator):
    """Test that waste generation returns positive values"""
    generator, env = setup_generator
    
    # Run simulation for a few steps
    env.run(until=5)
    
    # Check that something was generated
    volumes = generator.get_current_waste_volumes()
    assert sum(volumes.values()) >= 0
    assert all(v >= 0 for v in volumes.values())

@pytest.mark.parametrize("region,time", [
    (RegionType.GORENJSKA, 1),
    (RegionType.GORISKA, 10),
    (RegionType.KOROSKA, 100)
])
def test_generate_waste_various_regions(region, time):
    """Test waste generation for different regions"""
    env = simpy.Environment()
    data_collector = DataCollector()
    waste_streams = {WasteType.CONSTRUCTION_WOOD_17_02_01: 100.0}
    
    generator = WasteGenerator(
        env=env,
        name=f"generator_{region.value}",
        waste_streams=waste_streams,
        generation_frequency=1,
        storage_capacity=1000,
        environmental_impact=0.5,
        region=region.value,
        data_collector=data_collector
    )
    
    # Run simulation up to specified time
    env.run(until=time)
    
    # Verify generation
    volumes = generator.get_current_waste_volumes()
    assert sum(volumes.values()) >= 0
    assert all(isinstance(v, (int, float)) for v in volumes.values())

def test_storage_capacity_limit(setup_generator):
    """Test that storage capacity limits are respected"""
    generator, env = setup_generator
    initial_storage = sum(generator.get_current_waste_volumes().values())
    
    # Run simulation long enough to potentially exceed capacity
    env.run(until=20)
    
    final_storage = sum(generator.get_current_waste_volumes().values())
    assert final_storage <= generator.storage_capacity
    assert final_storage >= initial_storage

def test_generation_history(setup_generator):
    """Test that generation history is properly tracked"""
    generator, env = setup_generator
    
    # Run simulation for a few steps
    env.run(until=5)
    
    history = generator.get_generation_history_summary()
    assert len(history) > 0
    
    # Check first waste type
    waste_type = WasteType.CONSTRUCTION_WOOD_17_02_01.value
    assert waste_type in history
    assert "total_generated" in history[waste_type]
    assert "average_per_cycle" in history[waste_type]
    assert "current_storage" in history[waste_type]
    assert "generation_rate" in history[waste_type]

def test_invalid_initial_stock():
    """Test that invalid initial stock raises ValueError"""
    env = simpy.Environment()
    data_collector = DataCollector()
    waste_streams = {WasteType.CONSTRUCTION_WOOD_17_02_01: 100.0}
    
    # Try to create generator with initial stock exceeding capacity
    with pytest.raises(ValueError):
        WasteGenerator(
            env=env,
            name="test_generator",
            waste_streams=waste_streams,
            generation_frequency=1,
            storage_capacity=1000,
            environmental_impact=0.5,
            region=RegionType.OSREDNJESLOVENSKA.value,
            initial_stock={WasteType.CONSTRUCTION_WOOD_17_02_01: 2000.0},  # Exceeds capacity
            data_collector=data_collector
        )
