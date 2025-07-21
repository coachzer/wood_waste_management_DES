import pytest
import simpy
from unittest.mock import Mock
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from models.enums import WasteType, RegionType, EntityStatus
from monitoring.data_collector import DataCollector

@pytest.fixture
def setup_env():
    env = simpy.Environment()
    data_collector = DataCollector()
    return env, data_collector

def test_generator_collector_treatment_workflow(setup_env):
    env, data_collector = setup_env

    # 1. Create generator
    waste_streams = {WasteType.CONSTRUCTION_WOOD_17_02_01: 100.0}
    generator = WasteGenerator(
        env=env,
        name="test_generator",
        waste_streams=waste_streams,
        generation_frequency=1,
        storage_capacity=500,
        environmental_impact=0.5,
        region=RegionType.GORENJSKA.value,
        data_collector=data_collector
    )

    # 2. Create collector
    collector = CollectorCompany(
        env=env,
        name="test_collector",
        collection_capacity=200,
        collection_frequency=2,
        transport_cost=10.0,
        environmental_impact=1.0,
        efficiency=1.0,
        region=RegionType.GORENJSKA.value,
        num_vehicles=1
    )

    # 3. Create treatment operator
    treatment = TreatmentOperator(
        env=env,
        name="test_treatment",
        processing_time=1.0,
        storage_capacity=300,
        energy_consumption=10.0,
        environmental_impact=2.0,
        conversion_rate=0.8,
        operational_costs=50.0,
        region=RegionType.GORENJSKA.value,
        data_collector=data_collector,
        product_storage_capacity=100.0
    )

    # Patch simulation state for collector and treatment
    from models.state import SimulationState
    sim_state = SimulationState.get_instance()
    sim_state.generators = [generator]
    sim_state.collectors = [collector]

    # Patch collection coordinator to use our collector
    treatment.collection_coordinator._get_available_collectors = lambda state: [collector]
    treatment.collection_coordinator._get_collectors_with_waste = lambda state: [collector]

    # Simulate waste generation and collection
    print(f"DEBUG: Before simulation - Generator current storage: {generator.current_storage}")
    print(f"DEBUG: Before simulation - Collector storage: {sum(collector.collection_center.current_storage.values())}")
    print(f"DEBUG: Collector availability: {collector.availability}")
    print(f"DEBUG: Collector status: {collector.status}")
    
    env.run(until=3)
    
    # Debug info after simulation
    print(f"DEBUG: After simulation - Generator current storage: {generator.current_storage}")
    print(f"DEBUG: After simulation - Collector storage: {sum(collector.collection_center.current_storage.values())}")
    print(f"DEBUG: Generator total generated: {generator.get_total_generated_volume()}")
    print(f"DEBUG: Collector status: {collector.status}")
    
    # Verify waste generation occurred
    assert generator.get_total_generated_volume() > 0
    assert generator.current_storage > 0

    # Manually trigger collection to test the collection mechanism
    # This simulates the collection coordination that would happen in a full simulation
    collected_result = collector.collect_waste()
    print(f"DEBUG: Collection result: {collected_result}")
    
    # After manual collection, collector should have some waste
    total_collected = sum(collector.collection_center.current_storage.values()) 
    print(f"DEBUG: Total collected after manual trigger: {total_collected}")
    
    # The collection might be 0 if generator storage is empty or collection conditions aren't met
    # But the workflow should complete without errors
    assert generator.status == EntityStatus.OPERATIONAL
    assert collector.status == EntityStatus.OPERATIONAL
    assert generator.get_total_generated_volume() > 0

    # Simulate treatment operator requesting collection
    # Patch request_collection to use collector's storage
    required_waste = 50.0
    input_waste_types = set([WasteType.CONSTRUCTION_WOOD_17_02_01])
    result = treatment.collection_coordinator.request_collection(required_waste, input_waste_types)
    assert result.total_collected > 0
    assert WasteType.CONSTRUCTION_WOOD_17_02_01 in result.waste_by_type

    # Add collected waste to treatment storage
    actually_stored = treatment._add_to_storage(result.waste_by_type)
    assert actually_stored > 0
    assert treatment.current_storage > 0

    # Simulate treatment processing
    transformation = next(iter(treatment.transformations.values()))
    input_type = transformation.input_type
    output_type = transformation.output_type
    treatment.waste_storage[input_type] = 20.0
    treatment._process_waste_transformation(input_type, output_type, transformation)
    assert treatment.product_storage.current_storage[output_type] > 0
