import simpy
from models.config import get_uncertainty_set
from config.base_config import SIMULATION_DURATION, TIME_PERIOD, TOTAL_YEARS
from models.state import SimulationState
from monitoring.monitor import WasteMonitor
from utils.helpers import monitor_system

# Core components
from core.facility_builder import initialize_simulation_entities

# Optimization components
from optimization.objectives import (
    StorageUtilizationObjective,
    CollectionEfficiencyObjective,
    TreatmentEfficiencyObjective,
)
from optimization.strategies import OptimizationStrategy
from optimization.optimizer import WasteOptimizer
from optimization.visualization import OptimizationVisualizer
from optimization.stochastic import ScenarioGenerator

def setup_optimization(scenario_name: str = "Baseline"):
    # Get uncertainty set for specified scenario
    uncertainty_set = get_uncertainty_set(scenario_name)
    # Create scenario generator with proper uncertainty set
    scenario_generator = ScenarioGenerator(uncertainty_set)

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

def _check_year_transition(env, current_year, scenario_generator):
    """Handle year transition and parameter adjustments"""
    if env.now > 0 and env.now % TIME_PERIOD == 0:
        current_year = (env.now // TIME_PERIOD) + 1
        if current_year <= TOTAL_YEARS:
            print(f"\n=== Starting Year {current_year} at time {env.now} ===")
            # Adjust uncertainty parameters for the new year
            scenario_generator.adjust_parameters(
                waste_generation_multiplier=1.0 + (0.1 * (current_year - 1)),
                efficiency_multiplier=1.0 + (0.05 * (current_year - 1)),
            )
    return current_year

def _print_optimization_results(env, result):
    """Print detailed optimization results"""
    print(f"\n=== Optimization Results at Time {env.now} ===")
    print("Objective Scores (with risk measures):")
    for objective, score in result.scores.items():
        risk_measure = getattr(result, "risk_measures", {}).get(objective, 0.0)
        scenarios = getattr(result, "scenarios_evaluated", {}).get(objective, 1)
        # print(f"- {objective}:")
        # print(f"  Score: {score:.3f}")
        # print(f"  Risk Measure (VaR): {risk_measure:.3f}")
        # print(f"  Scenarios Evaluated: {scenarios}")

    _print_actions_and_suggestions(result)

def _print_actions_and_suggestions(result):
    """Print optimization actions and suggestions"""
    if result.actions:
        print("\nOptimization Actions:")
        for action in result.actions:
            confidence = getattr(action, "confidence", 1.0)
            # print(
            #     f"- {action.entity_type}: {action.parameter} adjusted by {action.adjustment}"
            #     f" (Confidence: {confidence:.2f})"
            # )

    if result.suggestions:
        print("\nRobustness Suggestions:")
        for suggestion in result.suggestions:
            print(f"- {suggestion}")

def optimization_process(env, optimizer, scenario_generator):
    """Run periodic optimization of the waste management system with year-based adjustments"""
    current_year = 1
    while True:
        # Check for year transition and update parameters if needed
        current_year = _check_year_transition(env, current_year, scenario_generator)

        # Run optimization
        result = optimizer.optimize()

        # Log optimization results
        _print_optimization_results(env, result)

        # Wait for next optimization cycle
        yield env.timeout(10)

def main():
    # Create simulation environment
    env = simpy.Environment()
    
    # Create monitor first so its data collector can be used
    waste_monitor = WasteMonitor()

    # Get baseline uncertainty set
    baseline_uncertainty = get_uncertainty_set("Baseline")

    # Create entities with baseline uncertainty set
    print("\nLoading simulation entities...")
    try:
        generators, collectors, treatment_operators = initialize_simulation_entities(
            env, 
            baseline_uncertainty,
            waste_monitor.data_collector
        )
    except ValueError as e:
        print(f"Error loading entities: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # Print facility data for debugging
        from models.facility_data import FacilityDataManager
        facility_manager = FacilityDataManager()
        facility_manager.load_data()
        for region, facilities in facility_manager.regions.items():
            print(f"\nRegion: {region}")
            for gen in facilities.generators:
                print(f"Generator {gen.id} waste types: {gen.waste_generation_rates.keys()}")
        raise

    # Initialize simulation state
    state = SimulationState.get_instance()
    state.initialize(generators, collectors, treatment_operators)

    # Store initial parameters for comparison
    initial_params = {
        "collection_rates": [c.collection_frequency for c in state.collectors],
        "processing_rates": [t.processing_time for t in state.treatment_operators],
    }

    # Create optimizer and scenario generator after state is initialized
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

    # Set up optimization process with scenario generator
    env.process(optimization_process(env, optimizer, scenario_generator))

    # Run simulation
    simulation_duration = SIMULATION_DURATION
    print(f"Starting simulation for {simulation_duration} time units...")
    print(
        f"Using stochastic optimization with {scenario_generator.num_scenarios} scenarios"
    )
    
    # Run simulation with demand satisfaction check
    def check_simulation_end(env, state):
        """Process to periodically check if all demands are met"""
        while True:
            if state.check_all_demands_met():
                print("\n=== All product demands have been met! ===")
                print("Current production vs targets:")
                for product, amount in state.total_products.items():
                    target = state.target_demands[product]
                    print(f"- {product}: {amount:.2f}/{target:.2f} m³")
                return True
            yield env.timeout(1)  # Check every time unit
            
    # Get simulation state instance
    sim_state = SimulationState.get_instance()
    
    # Start the checking process
    env.process(check_simulation_end(env, sim_state))
    
    # Run until either all demands are met or simulation duration is reached
    env.run(until=simulation_duration)
    
    # Print final production status
    print("\n=== Final Production Status ===")
    unmet = sim_state.get_unmet_demands()
    if any(demand > 0 for demand in unmet.values()):
        print("Some demands were not met:")
        for product, remaining in unmet.items():
            if remaining > 0:
                target = sim_state.target_demands[product]
                achieved = sim_state.total_products[product]
                print(f"- {product}: {achieved:.2f}/{target:.2f} m³ (remaining: {remaining:.2f} m³)")
    else:
        print("All demands were successfully met!")

    # Compare final parameters
    final_params = {
        "collection_rates": [c.collection_frequency for c in state.collectors],
        "processing_rates": [t.processing_time for t in state.treatment_operators],
    }
    print("\nParameter Evolution:")
    print("Initial:", initial_params)
    print("Final:", final_params)

    # Create visualizations
    waste_monitor.plot_temporal_analysis(
        simulation_duration
    )  # Generate all plots including material flow analysis
    visualizer = OptimizationVisualizer(optimizer.history)
    visualizer.plot_results("plots/optimization_results.png")

    return waste_monitor, optimizer

if __name__ == "__main__":
    monitor, optimizer = main()
