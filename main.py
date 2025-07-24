from config.base_config import get_scenario_with_strategies, list_available_scenarios
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy
from monitoring.mfa_visualization import create_material_flow_analysis
from monitoring.scenario_comparison import ScenarioComparison
import traceback

def extract_monitor_data(monitor):
    """Extract all relevant data from the monitor"""
    return {
        'generation_history': monitor.get_generation_history,
        'collection_history': monitor.get_collection_history,
        'processing_history': monitor.get_processing_history,
        'cost_history': monitor.get_cost_history,
        'overflow_history': monitor.get_overflow_history,
        'entity_status_history': monitor.get_entity_status_history
    }

def main():
    results = []
    mfa_files = []

    scenarios = list_available_scenarios()
    print(f"Available scenarios: {scenarios}")

    inventory_policies = list(InventoryPolicy)
    print(f"Available inventory policies: {inventory_policies}")

    stock_strategies = list(StockStrategy)
    print(f"Available stock strategies: {stock_strategies}")

    
    for scenario_name in scenarios:
        print(f"\n{'='*60}")
        print(f"Running base scenario: {scenario_name}")
        print(f"{'='*60}")
        
        for inventory_policy in InventoryPolicy:
            for stock_strategy in StockStrategy:
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

                    monitor_data = extract_monitor_data(manager.waste_monitor)
    
                    mfa_path = create_material_flow_analysis(
                        generation_history=monitor_data['generation_history'],
                        collection_history=monitor_data['collection_history'],
                        processing_history=monitor_data['processing_history'],
                        scenario_name=scenario_name,
                        inventory_policy=inventory_policy.value,
                        stock_strategy=stock_strategy.value
                    )
                    
                    mfa_files.append(mfa_path)
                    
                    results.append({
                        "base_scenario": scenario_name,
                        "scenario_name": scenario_config.name,
                        "inventory_policy": inventory_policy.value,
                        "stock_strategy": stock_strategy.value,
                        "monitor_data": monitor_data,
                        "mfa_path": mfa_path
                    })

                except Exception as e:
                    traceback.print_exc()
                    raise SystemExit(f"Simulation failed for scenario {scenario_name} with {inventory_policy.value}, {stock_strategy.value}") from e
    
    # Create comparison object AFTER all results are collected
    print(f"\n{'='*60}")
    print("Creating scenario comparison visualizations")
    print(f"{'='*60}")
    
    comparison = ScenarioComparison(results)  # Now results has data
    comparison.create_storage_heatmaps()
    comparison.create_temporal_comparison()
    comparison.create_cost_impact_comparison()
    comparison.create_summary_dashboard()
    print("Scenario comparison visualizations saved to plots/scenario_comparison/")

    print(f"\n{'='*60}")
    print("MFA Visualizations Created")
    print(f"{'='*60}")
    for mfa_path in mfa_files:
        print(f"  {mfa_path}")
    
    print(f"\nTotal simulations run: {len(results)}")
    print(f"Base scenarios: {len(scenarios)}")
    print(f"Strategy combinations per base scenario: {len(InventoryPolicy) * len(StockStrategy)}")

    return results
if __name__ == "__main__":
    all_results = main()
