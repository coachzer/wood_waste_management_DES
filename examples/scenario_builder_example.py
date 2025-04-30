"""
Example demonstrating how to use the ScenarioBuilder to load and validate scenarios.
This example shows:
1. Loading a predefined scenario
2. Basic validation
3. Accessing scenario data
"""

import sys
from pathlib import Path
from config.scenarios.scenario_builder import ScenarioBuilder

def get_project_root() -> Path:
    """Get project root directory"""
    return Path(__file__).parent.parent

def print_section(title):
    """Print a section header"""
    print("\n" + "="*50)
    print(title)
    print("="*50)

def main():
    # Create a scenario builder
    builder = ScenarioBuilder()
    
    print_section("Loading Baseline 2025 Scenario")
    project_root = get_project_root()
    config_path = project_root / 'config' / 'scenarios' / 'baseline_2025.json'
    config = builder.load_from_json(str(config_path)).build()
    print(f"Loaded scenario: {config.name}")
    
    print_section("Region Details")
    for region_name, region in config.regions.items():
        print(f"\nRegion: {region_name}")
        print("Generation Rates:")
        for waste_type, rate in region.generation_rates.items():
            print(f"  {waste_type.value}:")
            print(f"    Mean: {rate.mean:.2f}")
            print(f"    Std Dev: {rate.std:.2f}")
        
        print("\nCollection Parameters:")
        print(f"  Efficiency Mean: {region.collection.efficiency.mean:.2f}")
        print(f"  Efficiency Std Dev: {region.collection.efficiency.std:.2f}")
        print(f"  Collection Frequency: {region.collection.frequency:.1f}")
        print(f"  Collection Capacity: {region.collection.capacity:.1f}")
        print(f"  Storage Capacity: {region.storage_capacity:.1f}")
    
    print_section("Equipment Failure Parameters")
    print(f"Probability: {config.uncertainty_params.equipment_failure_probability:.3f}")
    print(f"Min Duration: {config.uncertainty_params.min_failure_duration:.1f}")
    print(f"Max Duration: {config.uncertainty_params.max_failure_duration:.1f}")
    
    print_section("Product Conversion Rates")
    for input_type, conversions in config.product_conversions.items():
        print(f"\n{input_type}:")
        for product, rate in conversions.items():
            print(f"  → {product}: {rate:.2f}")

    # Example of validation in practice
    print_section("Validation Example")
    try:
        is_valid = config.validate()
        print(f"Scenario validation: {'Passed' if is_valid else 'Failed'}")
        
        # Example validation details
        print("\nChecking specific aspects:")
        print(f"- Has valid name: {bool(config.name)}")
        print("- Region validations:")
        for region_name, region in config.regions.items():
            print(f"  {region_name}: {region.validate()}")
        print(f"- Uncertainty params validation: {config.uncertainty_params.validate()}")
        
    except Exception as e:
        print(f"Validation error: {str(e)}")

if __name__ == "__main__":
    main()
