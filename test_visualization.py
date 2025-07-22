#!/usr/bin/env python3

from main import main_single_scenario
from monitoring.scenario_comparison import ScenarioComparison

def test_visualization():
    """Quick test to verify visualization works with sample data"""
    
    print("Running single scenario test...")
    monitor = main_single_scenario("Baseline")
    
    # Create a mock results list for testing scenario comparison
    mock_results = [{
        "scenario_name": "Test_Baseline",
        "inventory_policy": "PUSH",
        "stock_strategy": "FULL_STOCK",
        "coordination_strategy": "from_json",
        "monitor": monitor
    }]
    
    print("Creating test visualizations...")
    comparison = ScenarioComparison(mock_results)
    
    # Test individual visualization components
    try:
        comparison.create_storage_heatmaps()
        print("✓ Storage heatmaps created successfully")
    except Exception as e:
        print(f"✗ Storage heatmaps failed: {e}")
    
    try:
        comparison.create_temporal_comparison()
        print("✓ Temporal comparison created successfully")
    except Exception as e:
        print(f"✗ Temporal comparison failed: {e}")
    
    try:
        comparison.create_summary_dashboard()
        print("✓ Summary dashboard created successfully")
    except Exception as e:
        print(f"✗ Summary dashboard failed: {e}")

if __name__ == "__main__":
    test_visualization()
