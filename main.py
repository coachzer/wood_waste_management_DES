from core.simulation_manager import SimulationManager
from config.base_config import get_uncertainty_set

def main():
    """Main simulation entry point"""
    # Initialize simulation manager
    manager = SimulationManager()
    
    # Get baseline uncertainty set and initialize entities
    baseline_uncertainty = get_uncertainty_set("Baseline")
    manager.initialize_entities(baseline_uncertainty)
    
    # Set up optimization
    manager.setup_optimization()
    
    # Set up simulation processes
    manager.setup_processes()
    
    # Run simulation
    manager.run_simulation()
    
    # Create visualizations
    manager.create_visualizations()
    
    return manager.waste_monitor, manager.optimizer

if __name__ == "__main__":
    monitor, optimizer = main()
