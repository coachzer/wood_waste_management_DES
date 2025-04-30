import pytest
import os
from config.scenarios.scenario_builder import (
    ScenarioBuilder,
    ScenarioConfig,
    RateConfig,
    CollectionConfig,
    RegionConfig,
    UncertaintyParams
)
from models.enums import WasteType

@pytest.fixture
def sample_json_path():
    return os.path.join('config', 'scenarios', 'baseline_2025.json')

def test_load_from_json(sample_json_path):
    """Test loading scenario from JSON file"""
    builder = ScenarioBuilder()
    config = builder.load_from_json(sample_json_path).build()
    
    # Verify basic structure
    assert isinstance(config, ScenarioConfig)
    assert config.name == "baseline_2025"
    assert "podravska" in config.regions
    
    # Verify region configuration
    region = config.regions["podravska"]
    assert isinstance(region, RegionConfig)
    assert region.storage_capacity == 1100.0
    
    # Verify generation rates
    rates = region.generation_rates
    assert WasteType.SAWDUST in rates
    assert rates[WasteType.SAWDUST].mean == 11.0
    assert rates[WasteType.SAWDUST].std == 2.5
    
    # Verify collection config
    collection = region.collection
    assert isinstance(collection, CollectionConfig)
    assert collection.frequency == 24.0
    assert collection.capacity == 1800.0
    assert collection.efficiency.mean == 0.9
    assert collection.efficiency.std == 0.08
    
    # Verify uncertainty parameters
    uncertainty = config.uncertainty_params
    assert isinstance(uncertainty, UncertaintyParams)
    assert uncertainty.equipment_failure_probability == 0.001
    assert uncertainty.min_failure_duration == 12.0
    assert uncertainty.max_failure_duration == 24.0
    
    # Verify product conversions
    conversions = config.product_conversions
    assert "sawdust" in conversions
    assert conversions["sawdust"]["wooden_packaging"] == 0.8

def test_validation():
    """Test configuration validation"""
    builder = ScenarioBuilder()
    
    # Test invalid mean
    with pytest.raises(ValueError):
        builder.regions["test"] = RegionConfig(
            generation_rates={
                WasteType.SAWDUST: RateConfig(mean=-1.0, std=1.0)
            },
            collection=CollectionConfig(
                efficiency=RateConfig(mean=0.9, std=0.1),
                frequency=24.0,
                capacity=1000.0
            ),
            storage_capacity=1000.0
        )
        builder.build()
    
    # Test invalid probability
    with pytest.raises(ValueError):
        builder.uncertainty_params = UncertaintyParams(
            equipment_failure_probability=1.5,  # Invalid: > 1
            min_failure_duration=12.0,
            max_failure_duration=24.0
        )
        builder.build()
    
    # Test invalid duration
    with pytest.raises(ValueError):
        builder.uncertainty_params = UncertaintyParams(
            equipment_failure_probability=0.1,
            min_failure_duration=24.0,
            max_failure_duration=12.0  # Invalid: < min_duration
        )
        builder.build()

def test_empty_scenario():
    """Test handling of empty scenario"""
    builder = ScenarioBuilder()
    with pytest.raises(ValueError):
        builder.build()  # Should fail validation due to empty name

def test_complete_scenario(sample_json_path):
    """Test complete scenario creation and validation"""
    builder = ScenarioBuilder()
    config = builder.load_from_json(sample_json_path).build()
    
    # Verify complete validation
    assert config.validate()
    
    # Test serialization potential (important for future features)
    assert hasattr(config, "__dict__")  # Ensure we can serialize if needed
