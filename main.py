from core.simulation_manager import SimulationManager
from config import get_uncertainty_set, get_scenario_by_params
from models.enums import InventoryPolicy, StockStrategy, CoordinationStrategy

def main():
    """Main simulation entry point - simplified configuration approach"""
    results = []
    
    # Option 1: Run all scenario combinations (comprehensive)
    for inventory_policy in InventoryPolicy:
        for stock_strategy in StockStrategy:
            for coordination_strategy in CoordinationStrategy:
                print(f"\n=== Running scenario: {inventory_policy.value} | {stock_strategy.value} | {coordination_strategy.value} ===")
                
                # Get scenario configuration that matches these parameters
                scenario_config = get_scenario_by_params(
                    inventory_policy=inventory_policy,
                    stock_strategy=stock_strategy,
                    coordination_strategy=coordination_strategy
                )
                
                # Initialize simulation manager
                manager = SimulationManager()
                
                # Get uncertainty set for this scenario
                uncertainty_set = get_uncertainty_set(scenario_config.name)
                
                # Initialize entities with scenario parameters
                manager.initialize_entities(uncertainty_set)
                
                # Set up simulation processes
                manager.setup_processes()
                
                # Run simulation
                manager.run_simulation()
                
                # Create visualizations
                manager.create_visualizations()
                
                results.append({
                    "scenario_name": scenario_config.name,
                    "inventory_policy": inventory_policy.value,
                    "stock_strategy": stock_strategy.value,
                    "coordination_strategy": coordination_strategy.value,
                    "monitor": manager.waste_monitor
                })
    
    return results

def main_single_scenario(scenario_name: str = "Baseline"):
    """Run a single scenario by name - for testing/debugging"""
    print(f"\n=== Running single scenario: {scenario_name} ===")
    
    # Initialize simulation manager
    manager = SimulationManager()
    
    # Get uncertainty set for this scenario
    uncertainty_set = get_uncertainty_set(scenario_name)
    
    # Initialize entities
    manager.initialize_entities(uncertainty_set)
    
    # Set up simulation processes
    manager.setup_processes()
    
    # Run simulation
    manager.run_simulation()
    
    # Create visualizations
    manager.create_visualizations()
    
    return manager.waste_monitor

if __name__ == "__main__":
    # For development: run single scenario
    # result = main_single_scenario("Baseline")
    
    # For full analysis: run all scenarios
    all_results = main()
