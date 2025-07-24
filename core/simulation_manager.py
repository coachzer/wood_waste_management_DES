import simpy
import traceback
from config.base_config import (
    SIMULATION_DURATION,
    ScenarioConfig
)
from models.enums import InventoryPolicy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.facility_data import FacilityDataManager
from core.decision_manager import DecisionTracker
from core.facility_builder import initialize_simulation_entities

class SimulationManager:
    """Manages simulation setup, execution, and monitoring"""
    
    def __init__(self):
        SimulationState._instance = None
        self.env = simpy.Environment()
        self.decision_tracker = DecisionTracker()
        self.waste_monitor = WasteMonitor(self.env, self.decision_tracker)
        self.state = SimulationState.get_instance()
        self.initial_params = {}
        
    def initialize_entities(self, scenario_config: ScenarioConfig) -> None:
        """Initialize simulation using the exact scenario the user requested."""
        try:
            uncertainty_set = scenario_config.to_uncertainty_set()

            stock_strategy     = scenario_config.stock_strategy
            inventory_policy   = scenario_config.inventory_policy

            dist_mode = (
                "balanced"
                if inventory_policy == InventoryPolicy.PUSH
                else "priority"
            )

            generators, collectors, operators = initialize_simulation_entities(
                self.env,
                uncertainty_set,
                self.decision_tracker,
                self.waste_monitor,
                dist_mode,       
                [],           
                stock_strategy,  
            )

            self.state.initialize(generators, collectors, operators)
            self._store_initial_parameters()

        except ValueError as e:
            self._handle_initialization_error(e)

    def _store_initial_parameters(self) -> None:
        """Store initial parameters for later comparison"""
        self.initial_params = {
            "collection_rates": {
                c.name: c.collection_frequency for c in self.state.collectors
            },
            "processing_rates": {
                t.name: t.processing_time for t in self.state.treatment_operators
            },
        }

    def _handle_initialization_error(self, error: ValueError) -> None:
        """Handle entity initialization errors"""
        print(f"Error loading entities: {str(error)}")
        print(traceback.format_exc())
        
        facility_manager = FacilityDataManager()
        facility_manager.load_data()
        for region, facilities in facility_manager.regions.items():
            print(f"\nRegion: {region}")
            for gen in facilities.generators:
                print(f"Generator {gen.id} waste types: {gen.waste_generation_rates.keys()}")
        raise

    def setup_processes(self) -> None:
        """Set up simulation processes"""
        self.env.process(
            self.waste_monitor.monitor_system_process(
                self.state.generators,
                self.state.collectors,
                self.state.treatment_operators,
            )
        )
        self.env.process(self._check_demand_satisfaction())

    def _check_demand_satisfaction(self):
        """Check if all demands are met"""
        demands_met = False
        while True:
            if self.state.check_all_demands_met() and not demands_met:
                demands_met = True
                self._print_demand_status()
            yield self.env.timeout(1)

    def run_simulation(self) -> None:
        """Run the simulation"""
        print(f"Starting simulation for {SIMULATION_DURATION} time units...")
        self.env.run(until=SIMULATION_DURATION)
        self._print_final_status()

    def _print_demand_status(self):
        """Print current demand satisfaction status"""
        print(f"\n=== All product demands have been met at time {self.env.now}! ===")
        print("Current production vs targets:")
        for product, amount in self.state.total_products.items():
            target = self.state.target_demands[product]
            print(f"- {product}: {amount:.2f}/{target:.2f} m³")

    def _print_final_status(self):
        """Print final simulation status"""
        print("\n=== Final Production Status ===")
        unmet = self.state.get_unmet_demands()
        if any(demand > 0 for demand in unmet.values()):
            print("Some demands were not met:")
            for product, remaining in unmet.items():
                if remaining > 0:
                    target = self.state.target_demands[product]
                    achieved = self.state.total_products[product]
                    print(f"- {product}: {achieved:.2f}/{target:.2f} m³ (remaining: {remaining:.2f} m³)")
        else:
            print("All demands were successfully met!")