import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
import simpy
from models.enums import WasteType, RegionType
from models.state import SimulationState
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from monitoring.data_collector import DataCollector

@pytest.fixture
def env():
    """Create a fresh SimPy environment for each test"""
    return simpy.Environment()

@pytest.fixture
def data_collector(env):
    """Create a data collector instance"""
    return DataCollector(env)

@pytest.fixture
def simulation_state():
    """Get a fresh simulation state instance"""
    state = SimulationState.get_instance()
    state.reset()  # Ensure clean state
    return state

@pytest.fixture
def basic_generator(env):
    """Create a basic waste generator for testing"""
    waste_streams = {
        WasteType.CONSTRUCTION_WOOD: 15.0,
        WasteType.SAWDUST: 8.0,
        WasteType.WASTE_WOODEN_PACKAGING: 10.0
    }
    initial_stock = {
        WasteType.CONSTRUCTION_WOOD: 50.0,
        WasteType.SAWDUST: 30.0,
        WasteType.WASTE_WOODEN_PACKAGING: 40.0
    }
    return WasteGenerator(
        env=env,
        name="TestGenerator",
        waste_streams=waste_streams,
        generation_frequency=1.0,
        storage_capacity=300.0,
        priority_level=1,
        environmental_impact=1.0,
        region="GORENJSKA",
        initial_stock=initial_stock
    )

@pytest.fixture
def basic_collector(env):
    """Create a basic collector company for testing"""
    return CollectorCompany(
        env=env,
        name="TestCollector",
        collection_capacity=250.0,
        collection_frequency=1.0,
        transport_cost=10.0,
        environmental_impact=1.0,
        efficiency=0.9,
        region="GORENJSKA",
        num_vehicles=3,
        vehicle_capacity=100.0
    )

@pytest.fixture
def basic_treatment(env, data_collector):
    """Create a basic treatment operator for testing"""
    return TreatmentOperator(
        env=env,
        name="TestTreatment",
        processing_time=1.0,
        storage_capacity=400.0,
        energy_consumption=50.0,
        environmental_impact=1.0,
        conversion_rate=0.8,
        operational_costs=100.0,
        region="GORENJSKA",
        data_collector=data_collector
    )

@pytest.fixture
def setup_basic_system(env, basic_generator, basic_collector, basic_treatment, simulation_state):
    """Setup a complete basic system with all components"""
    simulation_state.target_demands = {
        'wooden_furniture': 100.0,
        'wooden_packaging': 50.0,
        'paper_packaging': 30.0
    }
    return {
        'env': env,
        'generator': basic_generator,
        'collector': basic_collector,
        'treatment': basic_treatment,
        'state': simulation_state
    }
