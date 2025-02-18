import simpy
from models.config import SIMULATION_DURATION
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
from optimization.stochastic import ScenarioGenerator
from models.config import uncertainty_sets


def setup_optimization():
    # Create scenario generator with baseline uncertainty set
    scenario_generator = ScenarioGenerator(uncertainty_sets["Baseline"])

    # Create objectives with simplified risk-aware evaluation
    objectives = [
        StorageUtilizationObjective(
            weight=0.35, should_minimize=True, risk_aversion=0.3
        ),
        CollectionEfficiencyObjective(
            weight=0.35, should_minimize=False, risk_aversion=0.3
        ),
        TreatmentEfficiencyObjective(
            weight=0.30, should_minimize=False, risk_aversion=0.3
        ),
    ]

    # Set scenario generator for each objective
    for objective in objectives:
        objective.set_scenario_generator(scenario_generator)

    # Create strategy with higher threshold for robustness
    strategy = OptimizationStrategy(threshold=0.4)

    # Create optimizer
    optimizer = WasteOptimizer(objectives, strategy)

    return optimizer, scenario_generator


def optimization_process(env, optimizer):
    """Run periodic optimization of the waste management system"""
    while True:
        result = optimizer.optimize()

        # Log optimization results with stochastic measures
        print(f"\n=== Optimization Results at Time {env.now} ===")
        print("Objective Scores (with risk measures):")
        for objective, score in result.scores.items():
            risk_measure = getattr(result, "risk_measures", {}).get(objective, 0.0)
            scenarios = getattr(result, "scenarios_evaluated", {}).get(objective, 1)
            print(f"- {objective}:")
            print(f"  Score: {score:.3f}")
            print(f"  Risk Measure (VaR): {risk_measure:.3f}")
            print(f"  Scenarios Evaluated: {scenarios}")

        if result.actions:
            print("\nOptimization Actions:")
            for action in result.actions:
                confidence = getattr(action, "confidence", 1.0)
                print(
                    f"- {action.entity_type}: {action.parameter} adjusted by {action.adjustment}"
                    f" (Confidence: {confidence:.2f})"
                )

        if result.suggestions:
            print("\nRobustness Suggestions:")
            for suggestion in result.suggestions:
                print(f"- {suggestion}")

        # Wait for next optimization cycle
        yield env.timeout(10)


def create_simulation_entities(env, uncertainty_set=None):
    # GENERATORS (Optimized for increased output)
    # Large Furniture Manufacturers
    furniture_manufacturer1 = WasteGenerator(
        env=env,
        name="FurnitureCorp North",
        waste_streams={
            WasteType.SAWDUST: 25.0,  # Increased volume
            WasteType.WOOD_CUTTINGS: 20.0,  # Increased volume
            WasteType.SOLID_WOOD: 30.0,  # Increased volume
        },
        generation_frequency=0.5,  # More frequent generation
        storage_capacity=2000,  # Increased storage
        priority_level=2,  # Maintained priority
        uncertainty_set=uncertainty_set,
        environmental_impact="Moderate",
        region="North",
    )

    # Paper/Packaging Companies
    packaging_plant = WasteGenerator(
        env=env,
        name="PackagingCo East",
        waste_streams={
            WasteType.PAPER_PACKAGING: 35.0,  # Increased volume
            WasteType.WOOD_PACKAGING: 25.0,  # Increased volume
        },
        generation_frequency=0.4,  # More frequent generation
        storage_capacity=1200,  # Increased storage
        priority_level=1,
        uncertainty_set=uncertainty_set,
        environmental_impact="Low",
        region="East",
    )

    # Sawmills
    sawmill = WasteGenerator(
        env=env,
        name="SawmillPro South",
        waste_streams={
            WasteType.SAWDUST: 45.0,  # Increased volume
            WasteType.BARK: 30.0,  # Increased volume
            WasteType.WOOD_CUTTINGS: 25.0,  # Increased volume
        },
        generation_frequency=0.4,  # More frequent generation
        storage_capacity=800,  # Increased storage
        priority_level=1,
        uncertainty_set=uncertainty_set,
        environmental_impact="High",
        region="South",
    )

    # Construction Waste
    construction_waste = WasteGenerator(
        env=env,
        name="ConstructionWaste Central",
        waste_streams={
            WasteType.MIXED_WOOD: 50.0,  # Increased volume
            WasteType.WOOD_PACKAGING: 25.0,  # Increased volume
            WasteType.SOLID_WOOD: 20.0,  # Increased volume
        },
        generation_frequency=0.6,  # More frequent generation
        storage_capacity=1500,  # Increased storage
        priority_level=3,
        uncertainty_set=uncertainty_set,
        environmental_impact="Moderate",
        region="North",
    )

    # COLLECTORS (Optimized for balanced coverage)
    # Primary Regional Collector
    primary_collector = CollectorCompany(
        env=env,
        name="PrimaryWaste Solutions",
        collection_capacity=1000,  # Large capacity for main operations
        collection_frequency=1.5,
        transport_cost=95,  # Balanced cost
        environmental_impact="Low",
        efficiency=1.2,
        availability=True,
        region="North",
    )

    # Secondary Regional Collector
    secondary_collector = CollectorCompany(
        env=env,
        name="SecondaryWaste Services",
        collection_capacity=800,  # Medium capacity for support
        collection_frequency=1.2,
        transport_cost=85,
        environmental_impact="Low",
        efficiency=1.15,
        availability=True,
        region="South",
    )

    # Treatment operators with uncertainty sets
    # High-Capacity Processing Plant
    main_plant = TreatmentOperator(
        env=env,
        name="MainProcessingPlant",
        processing_time=0.3,
        storage_capacity=3000,  # Increased capacity
        energy_consumption=1.8,  # Balanced energy usage
        environmental_impact="Moderate",
        conversion_rate=0.96,  # High efficiency
        operational_costs=25,  # Standard operational costs
        region="North",
        uncertainty_set=uncertainty_set,
    )

    # Specialized Recycling Facility
    recycling_facility = TreatmentOperator(
        env=env,
        name="SpecializedRecycling",
        processing_time=0.4,
        storage_capacity=1500,
        energy_consumption=2.2,
        environmental_impact="Low",
        conversion_rate=0.94,
        operational_costs=35,
        region="South",
        uncertainty_set=uncertainty_set,
    )

    generators = [furniture_manufacturer1, packaging_plant, sawmill, construction_waste]
    collectors = [primary_collector, secondary_collector]
    treatment_operators = [main_plant, recycling_facility]

    return generators, collectors, treatment_operators


def main():
    # Create simulation environment
    env = simpy.Environment()

    # Create entities with baseline uncertainty set
    generators, collectors, treatment_operators = create_simulation_entities(
        env, uncertainty_sets["Baseline"]
    )

    # Initialize simulation state
    state = SimulationState.get_instance()
    state.initialize(generators, collectors, treatment_operators)

    # Store initial parameters for comparison
    initial_params = {
        "collection_rates": [c.collection_frequency for c in state.collectors],
        "processing_rates": [t.processing_capacity for t in state.treatment_operators],
    }

    # Create optimizer and scenario generator after state is initialized
    waste_monitor = WasteMonitor()
    optimizer, scenario_generator = setup_optimization()

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
    simulation_duration = SIMULATION_DURATION
    print(f"Starting simulation for {simulation_duration} time units...")
    print(
        f"Using stochastic optimization with {scenario_generator.num_scenarios} scenarios"
    )
    env.run(until=simulation_duration)

    # Compare final parameters
    final_params = {
        "collection_rates": [c.collection_frequency for c in state.collectors],
        "processing_rates": [t.processing_capacity for t in state.treatment_operators],
    }
    print("\nParameter Evolution:")
    print("Initial:", initial_params)
    print("Final:", final_params)

    # Create visualizations
    waste_monitor.plot_temporal_analysis()  # Generate all plots including material flow analysis
    visualizer = OptimizationVisualizer(optimizer.history)
    visualizer.plot_results("plots/optimization_results.png")

    return waste_monitor, optimizer


if __name__ == "__main__":
    monitor, optimizer = main()
