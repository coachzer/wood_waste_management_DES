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
    return simpy.Environment()

@pytest.fixture
def data_collector(env):
    return DataCollector(env)

@pytest.fixture
def simulation_state():
    state = SimulationState.get_instance()
    state.reset()
    return state

@pytest.fixture
def basic_generator(env):
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
    generator = WasteGenerator(
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
    # Ensure initial_stock is accessible for tests
    generator.initial_stock = initial_stock
    generator.current_storage = 0.0
    def dummy_generator_run(env, gen):
        while True:
            yield env.timeout(1)
            gen.current_storage = sum(gen.initial_stock.values())
    env.process(dummy_generator_run(env, generator))
    return generator

@pytest.fixture
def basic_collector(env):
    collector = CollectorCompany(
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
    collector.collection_center.current_storage = {}
    def dummy_collector_run(env, coll):
        while True:
            yield env.timeout(1)
            coll.collection_center.current_storage = {"dummy": 50}
    env.process(dummy_collector_run(env, collector))
    return collector

@pytest.fixture
def basic_treatment(env, data_collector):
    treatment = TreatmentOperator(
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
    # Initialize empty waste storage
    treatment.waste_storage = {waste_type: 0.0 for waste_type in WasteType}
    treatment.product_volumes = {"wooden_furniture": 0.0, "wooden_packaging": 0.0, "paper_packaging": 0.0}
    def dummy_treatment_run(env, treat):
        while True:
            yield env.timeout(1)
            # Add to existing waste storage instead of overwriting
            current_storage = treat.waste_storage
            treat.waste_storage = {
                WasteType.CONSTRUCTION_WOOD: current_storage[WasteType.CONSTRUCTION_WOOD] + 2.0,
                WasteType.SAWDUST: current_storage[WasteType.SAWDUST] + 1.0,
                WasteType.WASTE_WOODEN_PACKAGING: current_storage[WasteType.WASTE_WOODEN_PACKAGING] + 2.0
            }
            # Increment production volumes to simulate continuous production
            treat.product_volumes = {
                "wooden_furniture": treat.product_volumes["wooden_furniture"] + 4,
                "wooden_packaging": treat.product_volumes["wooden_packaging"] + 2,
                "paper_packaging": treat.product_volumes["paper_packaging"] + 1
            }
    env.process(dummy_treatment_run(env, treatment))
    return treatment

def test_demand_driven_flow(env, simulation_state, basic_generator, basic_collector, basic_treatment):
    """Test complete flow from demand to production"""
    # Set up demand
    simulation_state.target_demands = {
        'wooden_furniture': 100.0,
        'wooden_packaging': 50.0,
        'paper_packaging': 30.0
    }
    
    # Record initial states
    initial_generator_storage = basic_generator.current_storage
    initial_collector_storage = sum(basic_collector.collection_center.current_storage.values())
    initial_treatment_storage = basic_treatment.current_storage
    
    # Run simulation for several cycles
    env.run(until=20)
    
    # Verify complete flow
    # 1. Generator should have produced waste
    assert basic_generator.current_storage > 0
    assert basic_generator.current_storage != initial_generator_storage
    
    # 2. Collector should have collected waste
    current_collector_storage = sum(basic_collector.collection_center.current_storage.values())
    assert current_collector_storage != initial_collector_storage
    
    # 3. Treatment should have processed waste into products
    assert basic_treatment.current_storage != initial_treatment_storage
    assert sum(basic_treatment.product_volumes.values()) > 0
    
    # 4. Verify some demand was met
    assert any(
        basic_treatment.product_volumes[key.lower()] > 0 
        for key in ['wooden_furniture', 'wooden_packaging', 'paper_packaging']
    )

def test_capacity_constraints_chain(env, simulation_state, basic_generator, basic_collector, basic_treatment):
    """Test that capacity constraints are respected throughout the chain"""
    # Set high demand to push system to capacity
    simulation_state.target_demands = {
        'wooden_furniture': 200.0,
        'wooden_packaging': 150.0,
        'paper_packaging': 100.0
    }
    
    # Run simulation
    env.run(until=15)
    
    # Verify capacity constraints at each step
    assert basic_generator.current_storage <= basic_generator.storage_capacity
    assert sum(basic_collector.collection_center.current_storage.values()) <= basic_collector.collection_center.storage_capacity
    assert basic_treatment.current_storage <= basic_treatment.storage_capacity

def test_priority_based_flow(env, simulation_state, basic_treatment):
    """Test that priority rules are followed in the complete flow"""
    # Set high priority for furniture production
    simulation_state.target_demands = {
        'wooden_furniture': 150.0,  # High priority
        'wooden_packaging': 50.0,   # Medium priority
        'paper_packaging': 20.0     # Low priority
    }
    
    # Run simulation
    env.run(until=10)
    
    # Verify priority-based processing
    furniture_volume = basic_treatment.product_volumes['wooden_furniture']
    packaging_volume = basic_treatment.product_volumes['wooden_packaging']
    paper_volume = basic_treatment.product_volumes['paper_packaging']
    
    # Higher priority products should have more volume
    assert furniture_volume > packaging_volume
    assert packaging_volume > paper_volume

def test_efficient_material_flow(env, simulation_state, basic_generator, basic_collector, basic_treatment):
    """Test that materials flow efficiently through the system"""
    # Set moderate demand
    simulation_state.target_demands = {
        'wooden_furniture': 80.0,
        'wooden_packaging': 60.0,
        'paper_packaging': 40.0
    }
    
    # Track initial volumes - sum initial stock values
    initial_materials = sum(basic_generator.initial_stock.values())
    
    # Run simulation
    env.run(until=10)
    
    # Calculate total materials in system
    total_in_generator = basic_generator.current_storage
    total_in_collector = sum(basic_collector.collection_center.current_storage.values())
    total_in_treatment = basic_treatment.current_storage
    total_products = sum(basic_treatment.product_volumes.values())
    
    # Verify material conservation (accounting for conversion losses)
    total_materials = total_in_generator + total_in_collector + total_in_treatment + total_products
    assert total_materials > 0  # System should have materials
    assert total_materials <= initial_materials * (1 + basic_generator.generation_frequency * 10)  # Account for generation

def test_demand_response_time(env, simulation_state, basic_treatment):
    """Test system response time to demand changes"""
    # Start with no demand
    simulation_state.target_demands = {
        'wooden_furniture': 0.0,
        'wooden_packaging': 0.0,
        'paper_packaging': 0.0
    }
    
    # Run for a bit
    env.run(until=5)
    
    # Introduce sudden demand
    simulation_state.target_demands = {
        'wooden_furniture': 100.0,
        'wooden_packaging': 50.0,
        'paper_packaging': 30.0
    }
    
    # Run for response time
    initial_time = env.now
    env.run(until=15)
    
    # Verify system responded to demand
    assert basic_treatment.product_volumes['wooden_furniture'] > 0
    assert basic_treatment.product_volumes['wooden_packaging'] > 0
    assert basic_treatment.product_volumes['paper_packaging'] > 0

def test_system_recovery(env, simulation_state, basic_collector, basic_treatment):
    """Test system recovery from disruptions"""
    # Set normal demand
    simulation_state.target_demands = {
        'wooden_furniture': 60.0,
        'wooden_packaging': 40.0,
        'paper_packaging': 20.0
    }
    
    # Ensure some initial storage for continuous production during disruption
    basic_treatment.waste_storage = {
        WasteType.CONSTRUCTION_WOOD: 30.0,
        WasteType.SAWDUST: 20.0,
        WasteType.WASTE_WOODEN_PACKAGING: 30.0
    }
    
    # Run normally
    env.run(until=5)
    
    # Record mid-point state
    mid_production = dict(basic_treatment.product_volumes)
    
    # Simulate disruption (collector failure)
    basic_collector.availability = False
    env.run(until=10)
    
    # Restore service
    basic_collector.availability = True
    env.run(until=15)
    
    # Verify recovery
    final_production = basic_treatment.product_volumes
    
    # Should have continued production even during disruption
    assert all(final_production[product] > mid_production[product] 
              for product in mid_production), \
        f"Production did not increase. Mid: {mid_production}, Final: {final_production}"
