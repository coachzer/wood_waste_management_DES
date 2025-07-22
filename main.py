from core.simulation_manager import SimulationManager
from config import get_uncertainty_set, get_scenario_by_params
from models.enums import InventoryPolicy, StockStrategy
from monitoring.scenario_comparison import ScenarioComparison

def main():
    results = []
    
    for inventory_policy in InventoryPolicy:
        for stock_strategy in StockStrategy:
            print(f"\n=== Running scenario: {inventory_policy.value} | {stock_strategy.value} ===")
            
            scenario_config = get_scenario_by_params(
                inventory_policy=inventory_policy,
                stock_strategy=stock_strategy,
            )
            
            # Initialize simulation manager
            manager = SimulationManager()
            
            # Initialize entities with scenario parameters
            manager.initialize_entities(scenario_config)
            
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
                "coordination_strategy": "from_json", 
                "monitor": manager.waste_monitor
            })
    
    # Create scenario comparison visualizations
    print("\n=== Creating scenario comparison visualizations ===")
    comparison = ScenarioComparison(results)
    comparison.create_storage_heatmaps()
    comparison.create_temporal_comparison()
    comparison.create_cost_impact_comparison()
    comparison.create_pareto_front_plot()
    comparison.create_summary_dashboard()
    print("Scenario comparison visualizations saved to plots/scenario_comparison/")
    
    return results

if __name__ == "__main__":
    all_results = main()
