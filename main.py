import simpy
from models.enums import WasteType
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from models.state import SimulationState
from monitoring.monitor import WasteMonitor
from utils.helpers import monitor_system

# optimizer
from optimization.objectives import (
    StorageUtilizationObjective,
    CollectionEfficiencyObjective,
    TreatmentEfficiencyObjective,
)
from optimization.strategies import OptimizationStrategy
from optimization.optimizer import WasteOptimizer
from optimization.visualization import OptimizationVisualizer


def setup_optimization():
    # Create objectives
    objectives = [
        StorageUtilizationObjective(weight=0.3, should_minimize=True),
        CollectionEfficiencyObjective(weight=0.4, should_minimize=False),
        TreatmentEfficiencyObjective(weight=0.3, should_minimize=False),
    ]

    # Create strategy
    strategy = OptimizationStrategy(threshold=0.3)

    # Create optimizer
    optimizer = WasteOptimizer(objectives, strategy)

    return optimizer


def optimization_process(env, optimizer):
    """Run periodic optimization of the waste management system"""
    while True:
        result = optimizer.optimize()

        # Log optimization results
        print(f"\n=== Optimization Results at Time {env.now} ===")
        print("Scores:")
        for objective, score in result.scores.items():
            print(f"- {objective}: {score:.3f}")

        if result.actions:
            print("\nOptimization Actions:")
            for action in result.actions:
                print(
                    f"- {action.entity_type}: {action.parameter} adjusted by {action.adjustment}"
                )

        if result.suggestions:
            print("\nSuggestions:")
            for suggestion in result.suggestions:
                print(f"- {suggestion}")

        # Wait for next optimization cycle
        yield env.timeout(10)


def create_simulation_entities(env):
    # GENERATORS
    # Large Furniture Manufacturers
    furniture_manufacturer1 = WasteGenerator(
        env=env,
        name="FurnitureCorp North",
        waste_streams={
            WasteType.SAWDUST: 15.0,
            WasteType.WOOD_CUTTINGS: 12.0,
            WasteType.SOLID_WOOD: 20.0,
        },
        generation_frequency=0.01,  # Frequent generation
        storage_capacity=2000,  # Large storage
        priority_level=1,  # High priority
        randomness=0.15,  # Moderate variation
        std_dev=0.2,  # Standard deviation
        environmental_impact="Moderate",
        region="North",  # placeholder
    )

    # Paper/Packaging Companies
    packaging_plant = WasteGenerator(
        env=env,
        name="PackagingCo East",
        waste_streams={WasteType.PAPER_PACKAGING: 25.0, WasteType.WOOD_PACKAGING: 18.0},
        generation_frequency=0.01,
        storage_capacity=1500,
        priority_level=2,
        randomness=0.1,
        std_dev=0.15,
        environmental_impact="Low",
        region="East",
    )

    # Sawmills
    sawmill = WasteGenerator(
        env=env,
        name="SawmillPro South",
        waste_streams={
            WasteType.SAWDUST: 30.0,
            WasteType.BARK: 20.0,
            WasteType.WOOD_CUTTINGS: 15.0,
        },
        generation_frequency=0.01,  # Very frequent
        storage_capacity=3000,  # Large capacity
        priority_level=1,
        randomness=0.2,
        std_dev=0.25,
        environmental_impact="High",
        region="South",
    )

    # Construction Waste
    construction_waste = WasteGenerator(
        env=env,
        name="ConstructionWaste Central",
        waste_streams={
            WasteType.MIXED_WOOD: 40.0,
            WasteType.WOOD_PACKAGING: 15.0,
            WasteType.SOLID_WOOD: 10.0,
        },
        generation_frequency=0.01,
        storage_capacity=2500,
        priority_level=3,
        randomness=0.25,
        std_dev=0.3,
        environmental_impact="Moderate",
        region="North",
    )

    # COLLECTORS
    # Large Regional Collector
    regional_collector = CollectorCompany(
        env=env,
        name="RegionalWaste Solutions",
        collection_capacity=500,
        collection_frequency=0.1,
        transport_cost=80,
        environmental_impact="Low",
        efficiency=1,
        availability=True,
        strategy="collaborative",
        region="North",
    )

    # Specialized Wood Waste Collector
    specialized_collector = CollectorCompany(
        env=env,
        name="WoodWaste Specialists",
        collection_capacity=250,
        collection_frequency=0.5,
        transport_cost=60,
        environmental_impact="Low",
        efficiency=1,
        availability=True,
        strategy="competitive",
        region="South",
    )

    # Multi-Regional Collector
    multi_regional = CollectorCompany(
        env=env,
        name="MultiRegional Services",
        collection_capacity=350,
        collection_frequency=0.1,
        transport_cost=100,
        environmental_impact="Moderate",
        efficiency=1,
        availability=True,
        strategy="collaborative",
        region="East",
    )

    # TREATMENT OPERATORS
    # Biomass Energy Plant
    # biomass_plant = TreatmentOperator(
    #     env=env,
    #     name="BioPower Solutions",
    #     processing_capacity=30,
    #     processing_time=10,
    #     storage_capacity=4000,
    #     energy_consumption=2.0,
    #     environmental_impact="Low",
    #     conversion_rate=0.95,
    #     operational_costs=15,
    #     region="North",
    # )

    # # Recycling Facility
    # recycling_facility = TreatmentOperator(
    #     env=env,
    #     name="EcoRecycle Center",
    #     processing_capacity=50,
    #     processing_time=20,
    #     storage_capacity=3000,
    #     energy_consumption=1.5,
    #     environmental_impact="Low",
    #     conversion_rate=0.90,
    #     operational_costs=12,
    #     region="South",
    # )

    # # Composting Facility
    # composting_facility = TreatmentOperator(
    #     env=env,
    #     name="GreenCompost Facility",
    #     processing_capacity=40,
    #     processing_time=12,
    #     storage_capacity=2500,
    #     energy_consumption=1.0,
    #     environmental_impact="Low",
    #     conversion_rate=0.85,
    #     operational_costs=8,
    #     region="East",
    # )

    # ADJUSTED
    # Biomass Energy Plant
    biomass_plant = TreatmentOperator(
        env=env,
        name="BioPower Solutions",
        processing_capacity=60,  # Doubled from 30
        processing_time=0.2,  # Halved from 10
        storage_capacity=6000,  # Increased from 4000
        energy_consumption=3.0,  # Adjusted for increased capacity
        environmental_impact="Moderate",  # Changed due to higher intensity
        conversion_rate=0.95,
        operational_costs=25,  # Increased for higher capacity
        region="North",
    )

    # Recycling Facility
    recycling_facility = TreatmentOperator(
        env=env,
        name="EcoRecycle Center",
        processing_capacity=100,  # Doubled from 50
        processing_time=0.4,  # Halved from 20
        storage_capacity=5000,  # Increased from 3000
        energy_consumption=2.5,  # Adjusted
        environmental_impact="Moderate",
        conversion_rate=0.92,  # Slightly improved
        operational_costs=20,  # Adjusted for scale
        region="South",
    )

    # Composting Facility
    composting_facility = TreatmentOperator(
        env=env,
        name="GreenCompost Facility",
        processing_capacity=80,  # Doubled from 40
        processing_time=0.3,  # Halved from 12
        storage_capacity=4000,  # Increased from 2500
        energy_consumption=2.0,  # Adjusted
        environmental_impact="Low",
        conversion_rate=0.88,  # Slightly improved
        operational_costs=15,  # Adjusted for scale
        region="East",
    )

    generators = [furniture_manufacturer1, packaging_plant, sawmill, construction_waste]

    collectors = [regional_collector, specialized_collector, multi_regional]

    treatment_operators = [biomass_plant, recycling_facility, composting_facility]

    return generators, collectors, treatment_operators


def main():
    # Create simulation environment
    env = simpy.Environment()

    generators, collectors, treatment_operators = create_simulation_entities(env)

    # After creating all entities but before starting any processes
    state = SimulationState.get_instance()
    state.initialize(generators, collectors, treatment_operators)

    # Store initial parameters for comparison
    initial_params = {
        "collection_frequencies": [c.collection_frequency for c in state.collectors],
        "processing_capacities": [
            t.processing_capacity for t in state.treatment_operators
        ],
    }

    # Add debug print
    # print("\nInitial state:")
    # print(f"Generators registered: {len(state.generators)}")
    # for g in state.generators:
    #     print(
    #         f"Generator {g.name}: Region={g.region}, Storage={g.current_storage}/{g.storage_capacity}"
    #     )

    # print(f"Collectors registered: {len(state.collectors)}")
    # for c in state.collectors:
    #     print(
    #         f"Collector {c.name}: Region={c.region}, Collection Capacity={c.collection_capacity}"
    #     )

    # print(f"Treatment Operators registered: {len(state.treatment_operators)}")
    # for t in state.treatment_operators:
    #     print(
    #         f"Treatment Operator {t.name}: Region={t.region}, Processing Capacity={t.processing_capacity}"
    #     )

    # Create optimizer after state is initialized
    waste_monitor = WasteMonitor()
    optimizer = setup_optimization()

    # Set up monitoring process
    env.process(
        monitor_system(
            env,
            waste_monitor,
            state.generators,
            state.collectors,
            state.treatment_operators,
        )
    )

    # Set up optimization process
    env.process(optimization_process(env, optimizer))

    # Run simulation
    simulation_duration = 101
    print(f"Starting simulation for {simulation_duration} time units...")
    env.run(until=simulation_duration)

    # Compare final parameters
    final_params = {
        "collection_frequencies": [c.collection_frequency for c in state.collectors],
        "processing_capacities": [
            t.processing_capacity for t in state.treatment_operators
        ],
    }
    print("Parameter Evolution:", initial_params, "->", final_params)

    # Create visualizations
    visualizer = OptimizationVisualizer(optimizer.history)
    visualizer.plot_results("plots/optimization_results.png")

    return waste_monitor, optimizer


if __name__ == "__main__":
    monitor, optimizer = main()
