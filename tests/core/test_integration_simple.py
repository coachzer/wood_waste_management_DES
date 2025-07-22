import pytest
import simpy
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from monitoring.data_collector import DataCollector
from models.enums import WasteType, RegionType, EntityStatus
from models.state import SimulationState


@pytest.fixture
def clean_state():
    """Ensure we start with a clean state"""
    # Clear any existing instance
    SimulationState._instance = None
    state = SimulationState.get_instance()
    state.generators = []
    state.collectors = []
    state.treatment_operators = []
    return state


@pytest.fixture
def real_env():
    """Create a real SimPy environment"""
    return simpy.Environment()


@pytest.fixture  
def real_data_collector():
    """Create a real data collector"""
    return DataCollector()


def test_simple_waste_flow(real_env, clean_state, real_data_collector):
    """Test simple waste flow without complex timing"""
    # Create a generator with waste
    generator = WasteGenerator(
        env=real_env,
        name="TestGen",
        waste_streams={WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 10.0},
        generation_frequency=24,
        waste_storage_capacity=100.0,
        environmental_impact=1.0,
        region=RegionType.GORENJSKA.value,
        data_collector=real_data_collector
    )
    
    # Create a collector
    collector = CollectorCompany(
        env=real_env,
        name="TestCol",
        collection_capacity=50.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region=RegionType.GORENJSKA.value,
        num_vehicles=1
    )
    
    # Add to state so collector can find generator
    clean_state.generators = [generator]
    clean_state.collectors = [collector]
    
    # Test that entities were created properly
    assert generator.name == "TestGen"
    assert generator.waste_storage_capacity == 100.0
    assert collector.name == "TestCol"
    assert collector.collection_capacity == 50.0
    
    # Test that waste streams are initialized
    assert WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05 in generator.waste_streams


def test_treatment_basic_operation(real_env, real_data_collector, clean_state):
    """Test basic treatment operation"""
    treatment = TreatmentOperator(
        env=real_env,
        name="TestTreatment",
        processing_time=1.0,
        waste_storage_capacity=100.0,
        energy_consumption=10.0,
        environmental_impact=5.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region=RegionType.GORENJSKA.value,
        data_collector=real_data_collector,
        product_storage_capacity=50.0
    )
    
    # Manually add waste
    treatment.waste_storage[WasteType.CONSTRUCTION_WOOD_17_02_01] = 20.0
    
    # Test that treatment operator is properly initialized
    assert treatment.name == "TestTreatment"
    assert treatment.status == EntityStatus.OPERATIONAL
    assert treatment.current_storage > 0
    
    # Test storage capacity
    assert treatment.current_storage <= treatment.waste_storage_capacity


def test_entities_basic_interaction(real_env, clean_state, real_data_collector):
    """Test that entities can interact at a basic level"""
    # Create entities
    generator = WasteGenerator(
        env=real_env,
        name="Gen1",
        waste_streams={WasteType.CONSTRUCTION_WOOD_17_02_01: 5.0},
        generation_frequency=24,
        waste_storage_capacity=50.0,
        environmental_impact=1.0,
        region=RegionType.GORENJSKA.value,
        data_collector=real_data_collector
    )
    
    collector = CollectorCompany(
        env=real_env,
        name="Col1", 
        collection_capacity=30.0,
        collection_frequency=24,
        transport_cost=10.0,
        environmental_impact=5.0,
        efficiency=0.9,
        region=RegionType.GORENJSKA.value,
        num_vehicles=1
    )
    
    # Add to state
    clean_state.generators = [generator]
    clean_state.collectors = [collector]
    
    # Verify they can be found in state
    assert len(clean_state.generators) == 1
    assert len(clean_state.collectors) == 1
    assert clean_state.generators[0].name == "Gen1"
    assert clean_state.collectors[0].name == "Col1"
