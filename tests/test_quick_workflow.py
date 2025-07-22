"""
Quick workflow test for debugging and development.

This is a simplified version of the full workflow test that focuses on
basic functionality and can be run quickly during development.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.simulation_manager import SimulationManager
from config import get_uncertainty_set, get_scenario_by_params
from models.enums import InventoryPolicy, StockStrategy, CoordinationStrategy
from models.distances import get_distance
from models.state import SimulationState


def quick_config_test():
    """Test basic configuration loading"""
    print("🔧 Testing configuration...")
    
    try:
        # Test scenario loading
        scenario_config = get_scenario_by_params(
            inventory_policy=InventoryPolicy.PUSH,
            stock_strategy=StockStrategy.FULL_STOCK,
            coordination_strategy=CoordinationStrategy.COMPETITIVE
        )
        assert scenario_config is not None
        
        # Test uncertainty set loading
        uncertainty_set = get_uncertainty_set(scenario_config.name)
        assert uncertainty_set is not None
        
        print(f"✅ Configuration loaded: {scenario_config.name}")
        return True
        
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return False


def quick_distance_test():
    """Test basic distance system"""
    print("📍 Testing distances...")
    
    try:
        from models.enums import RegionType
        
        # Test a few key distances
        distance_lj_mb = get_distance(RegionType.OSREDNJESLOVENSKA, RegionType.PODRAVSKA)
        distance_kp_ms = get_distance(RegionType.OBALNO_KRASKA, RegionType.POMURSKA)
        
        assert distance_lj_mb > 0
        assert distance_kp_ms > 0
        
        print(f"✅ Distances working: Ljubljana-Maribor: {distance_lj_mb}km, Koper-Murska Sobota: {distance_kp_ms}km")
        return True
        
    except Exception as e:
        print(f"❌ Distance test failed: {e}")
        return False


def quick_simulation_test():
    """Test basic simulation run"""
    print("🔄 Testing simulation...")
    
    try:
        # Setup simulation
        scenario_config = get_scenario_by_params(
            inventory_policy=InventoryPolicy.PUSH,
            stock_strategy=StockStrategy.FULL_STOCK,
            coordination_strategy=CoordinationStrategy.COMPETITIVE
        )
        uncertainty_set = get_uncertainty_set(scenario_config.name)
        
        manager = SimulationManager()
        manager.initialize_entities(uncertainty_set)
        
        # Check entities were created
        state = SimulationState.get_instance()
        assert len(state.generators) > 0
        assert len(state.collectors) > 0
        assert len(state.treatment_operators) > 0
        
        print(f"✅ Simulation setup: {len(state.generators)} generators, {len(state.collectors)} collectors, {len(state.treatment_operators)} treatment facilities")
        
        # Try a very short simulation run
        manager.setup_processes()
        
        # Run for just 1 day to test basic functionality
        import simpy
        manager.env.run(until=1)
        
        print("✅ Basic simulation run completed")
        return True
        
    except Exception as e:
        print(f"❌ Simulation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_quick_test():
    """Run quick test suite"""
    print("🚀 Running quick workflow test...\n")
    
    tests = [
        ("Configuration", quick_config_test),
        ("Distance System", quick_distance_test),
        ("Simulation Setup", quick_simulation_test)
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        if test_func():
            passed += 1
        else:
            print(f"❌ {name} failed")
    
    print(f"\n📋 Quick Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All quick tests passed!")
        return True
    else:
        print("⚠️  Some tests failed")
        return False


if __name__ == "__main__":
    success = run_quick_test()
    sys.exit(0 if success else 1)
