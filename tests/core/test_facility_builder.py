import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import pytest
from simpy import Environment
from core.facility_builder import FacilityBuilder
from models.facility_data import FacilityDataManager
from monitoring.data_collector import DataCollector
from models.enums import RegionType, WasteType, OutputType

class MockGenData:
    def __init__(self, waste_storage_capacity=1000):
        self.id = "test_generator"
        self.waste_generation_rates = {WasteType.CONSTRUCTION_WOOD_17_02_01.value: 100}
        self.generation_frequency = 1
        self.waste_storage_capacity = waste_storage_capacity
        self.environmental_impact = 0.5
        self.initial_stock = None

@pytest.fixture
def setup_builder():
    env = Environment()
    facility_manager = FacilityDataManager()
    data_collector = DataCollector()
    return FacilityBuilder(env=env, 
                          facility_manager=facility_manager, 
                          data_collector=data_collector)

def test_facility_builder_initialization(setup_builder):
    """Test that FacilityBuilder initializes correctly"""
    assert setup_builder is not None
    assert isinstance(setup_builder.env, Environment)
    assert isinstance(setup_builder.facility_manager, FacilityDataManager)
    assert isinstance(setup_builder.data_collector, DataCollector)

def test_create_generator(setup_builder):
    """Test generator creation with valid parameters"""
    gen_data = MockGenData()
    generator = setup_builder.create_generator(gen_data, RegionType.OSREDNJESLOVENSKA)
    
    assert generator.name == "test_generator"
    assert WasteType.CONSTRUCTION_WOOD_17_02_01 in generator.waste_streams
    assert generator.waste_storage_capacity == 1000
    assert generator.generation_frequency == 1

@pytest.mark.parametrize("capacity", [-1, 0, 1000000.0])
def test_create_facility_capacity_limits(setup_builder, capacity):
    """Test generator creation with different capacity values"""
    gen_data = MockGenData(waste_storage_capacity=capacity)
    
    if capacity <= 0:
        with pytest.raises(ValueError):
            setup_builder.create_generator(gen_data, RegionType.OSREDNJESLOVENSKA)
    else:
        generator = setup_builder.create_generator(gen_data, RegionType.OSREDNJESLOVENSKA)
        assert generator.waste_storage_capacity == capacity
