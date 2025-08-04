from datetime import time
from config.base_config import get_scenario_with_strategies, list_available_scenarios
from core.facility_builder import print_failure_analysis
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy
from monitoring.mfa_visualization import create_material_flow_analysis
from monitoring.scenario_comparison import ScenarioComparison
import traceback
import time

def run_single_simulation(scenario_name: str, inventory_policy: InventoryPolicy, stock_strategy: StockStrategy) -> dict:
    """Run a single simulation configuration and return results"""
    print(f"\n=== Running: {scenario_name} | {inventory_policy.value} | {stock_strategy.value} ===")
    
    try:
        scenario_config = get_scenario_with_strategies(
            base_scenario_name=scenario_name,
            inventory_policy=inventory_policy,
            stock_strategy=stock_strategy
        )
        
        manager = SimulationManager()
        manager.initialize_entities(scenario_config)
        manager.setup_processes()
        manager.run_simulation()

        monitor_data = manager.get_monitor_data()

        mfa_path = create_material_flow_analysis(
            generation_history=monitor_data['generation_history'],
            collection_history=monitor_data['collection_history'],
            processing_history=monitor_data['processing_history'],
            scenario_name=scenario_name,
            inventory_policy=inventory_policy.value,
            stock_strategy=stock_strategy.value
        )

        print_failure_analysis()
        
        return {
            "base_scenario": scenario_name,
            "scenario_name": scenario_config.name,
            "inventory_policy": inventory_policy.value,
            "stock_strategy": stock_strategy.value,
            "monitor_data": monitor_data,
            "mfa_path": mfa_path
        }

    except Exception as e:
        traceback.print_exc()
        raise SystemExit(f"Simulation failed for scenario {scenario_name} with {inventory_policy.value}, {stock_strategy.value}") from e

def main():
    """Main simulation runner - orchestrates all scenario combinations"""
    start_time = time.time()
    print(f"\n{'='*60}")
    results = []
    mfa_files = []

    scenarios = list_available_scenarios()
    inventory_policies = list(InventoryPolicy)
    stock_strategies = list(StockStrategy)
    
    print(f"Available scenarios: {scenarios}")
    print(f"Available inventory policies: {[p.value for p in inventory_policies]}")
    print(f"Available stock strategies: {[s.value for s in stock_strategies]}")
    
    total_combinations = len(scenarios) * len(inventory_policies) * len(stock_strategies)
    print(f"\nTotal simulation combinations to run: {total_combinations}")
    
    # Run all scenario combinations
    for scenario_name in scenarios:
        print(f"\n{'='*60}")
        print(f"Running base scenario: {scenario_name}")
        print(f"{'='*60}")
        
        for inventory_policy in inventory_policies:
            for stock_strategy in stock_strategies:
                # Run single simulation
                result = run_single_simulation(scenario_name, inventory_policy, stock_strategy)
                results.append(result)
                mfa_files.append(result["mfa_path"])
    
    # Create comparison visualizations
    print(f"\n{'='*60}")
    print("Creating scenario comparison visualizations")
    print(f"{'='*60}")
    comparison = ScenarioComparison(results)
    comparison.create_storage_heatmaps()
    comparison.create_temporal_comparison()
    comparison.create_cost_impact_comparison()
    comparison.create_summary_dashboard()
    print("Scenario comparison visualizations saved to plots/scenario_comparison/")

    # Print summary
    print(f"\n{'='*60}")
    print("SIMULATION BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"Total simulations run: {len(results)}")
    print(f"Base scenarios: {len(scenarios)}")
    print(f"Strategy combinations per base scenario: {len(inventory_policies) * len(stock_strategies)}")

    # Print MFA files
    print("\nMFA Visualizations Created:")
    for mfa_path in mfa_files:
        print(f"  {mfa_path}")
        
    # Print total execution time
    print(f"\n{'='*60}")
    print("All simulations completed successfully!")
    print(f"Results saved to: {len(results)} simulation results")
    print(f"Material Flow Analysis files saved to: {len(mfa_files)} MFA files")
    print(f"\nTotal execution time: {time.time() - start_time:.2f} seconds")    

    return results

if __name__ == "__main__":
    all_results = main()