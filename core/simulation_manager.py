import simpy
import traceback
from typing import List, Dict, Any
from config.base_config import (
    ScenarioConfig
)
from config.constants import SIMULATION_DURATION
from core.transport_manager import PointToPointTransport
from models.enums import RegionType
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from models.facility_data import FacilityDataManager
from core.facility_builder import FacilityBuilder
from core.kanban_manager import KanbanManager
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator

class SimulationManager:
    """Manages complete simulation lifecycle - setup, execution, and monitoring"""
    
    def __init__(self):
        # Reset simulation state
        SimulationState._instance = None
        
        # Core simulation components
        self.env = simpy.Environment()
        self.waste_monitor = WasteMonitor(self.env)
        self.transport_manager = PointToPointTransport()

        # Kanban
        self.kanban_manager = KanbanManager()
        
        # Data and building components
        self.facility_manager = FacilityDataManager()
        self.facility_builder = None
        
        # Simulation state
        self.state = SimulationState.get_instance()
        
    def initialize_entities(self, scenario_config: ScenarioConfig) -> None:
        """Single point of entity initialization and setup"""
        try:
            # Load facility data
            self.facility_manager.load_data()
            
            # Create facility builder with scenario configuration
            uncertainty_set = scenario_config.to_uncertainty_set()

            self.facility_builder = FacilityBuilder(
                env=self.env,
                facility_manager=self.facility_manager,
                waste_monitor=self.waste_monitor,
                uncertainty_set=uncertainty_set,
                transport_manager=self.transport_manager,
                kanban_manager=self.kanban_manager
            )
            
            # Build all facilities
            generators, collectors, processors = self._build_all_facilities(scenario_config)
            
            # Distribute demand among processors
            self._distribute_demand(processors)
            
            # Initialize simulation state
            self.state.initialize(generators, collectors, processors)
            
            print("Initialized simulation with:")
            print(f"  - {len(generators)} generators")
            print(f"  - {len(collectors)} collectors") 
            print(f"  - {len(processors)} processors")

        except ValueError as e:
            self._handle_initialization_error(e)

    def _build_all_facilities(self, scenario_config: ScenarioConfig) -> tuple[List[WasteGenerator], List[CollectorCompany], List[TreatmentOperator]]:
        """Build all facilities for all regions using the facility builder"""
        generators = []
        collectors = []
        processors = []

        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if not facilities:
                continue
                
            # Build generators for this region
            for gen_data in facilities.generators:
                generator = self.facility_builder.create_generator(
                    gen_data, region, scenario_config.stock_strategy,
                    scenario_config.inventory_policy
                )
                generators.append(generator)

            # Build collectors for this region
            for col_data in facilities.collectors:
                collector = self.facility_builder.create_collector(
                    col_data, region, scenario_config.stock_strategy,
                    scenario_config.inventory_policy
                )
                collectors.append(collector)

            # Build processors for this region
            for proc_data in facilities.processors:
                processor = self.facility_builder.create_processor(proc_data, region, scenario_config.stock_strategy, scenario_config.inventory_policy)
                processors.append(processor)

        return generators, collectors, processors

    def _distribute_demand(self, processors: List[TreatmentOperator]) -> None:
        """Distribute national demand among processors by output type"""
        # Group processors by their output types
        processor_by_output = {}
        for processor in processors:
            for transformation in processor.transformations.values():
                output_type_str = transformation.output_type.value
                if output_type_str not in processor_by_output:
                    processor_by_output[output_type_str] = []
                processor_by_output[output_type_str].append(processor)
        
        # Distribute demand evenly among processors for each product type
        national_demand = self.facility_manager.demand
        for product_type, total_demand in national_demand.items():
            processors_for_product = processor_by_output.get(product_type, [])
            if processors_for_product:
                demand_per_processor = total_demand / len(processors_for_product)
                print(f"Distributing {product_type} demand {total_demand} among {len(processors_for_product)} processors")
                for processor in processors_for_product:
                    processor.demand = demand_per_processor
                    print(f"Assigned {demand_per_processor:.2f} m³ {product_type} demand to {processor.name}")

    def _handle_initialization_error(self, error: ValueError) -> None:
        """Handle entity initialization errors with detailed debugging"""
        print(f"Error loading entities: {str(error)}")
        print("Debug information:")
        
        for region, facilities in self.facility_manager.regions.items():
            print(f"\nRegion: {region}")
            for gen in facilities.generators:
                print(f"  Generator {gen.id} waste types: {gen.waste_generation_rates.keys()}")
        
        traceback.print_exc()
        raise

    def setup_processes(self) -> None:
        """Set up all simulation processes"""
        # Start monitoring process
        self.env.process(
            self.waste_monitor.monitor_system_process(
                self.state.generators,
                self.state.collectors,
                self.state.treatment_operators,
            )
        )
        
        # Start demand satisfaction checking
        self.env.process(self._check_demand_satisfaction())

    def run_simulation(self) -> None:
        """Execute the simulation"""
        print(f"Starting simulation for {SIMULATION_DURATION} time units...")
        self.env.run(until=SIMULATION_DURATION)
        self._print_final_status()

    def get_monitor_data(self) -> Dict[str, Any]:
        """Extract all relevant monitoring data"""
        return {
            'generation_history': self.waste_monitor.get_generation_history,
            'collection_history': self.waste_monitor.get_collection_history,
            'processing_history': self.waste_monitor.get_processing_history,
            'environmental_history': self.waste_monitor.get_environmental_history,
            'event_history': self.waste_monitor.get_event_history,
            'entity_status_history': self.waste_monitor.get_entity_status_history,
            'final_summary': {
                'simulation_time': self.env.now,
                'total_products': self.state.total_products,
                'target_demands': self.state.target_demands,
                'unmet_demands': self.state.get_unmet_demands()
            }
        }

    def _check_demand_satisfaction(self):
        """Monitor and report when all demands are satisfied"""
        demands_met = False
        while True:
            if self.state.check_all_demands_met() and not demands_met:
                demands_met = True
                self._print_demand_status()
            yield self.env.timeout(1)

    def _print_demand_status(self):
        """Print current demand satisfaction status"""
        print(f"\n=== All product demands have been met at time {self.env.now}! ===")
        print("Current production vs targets:")
        for product, amount in self.state.total_products.items():
            target = self.state.target_demands[product]
            print(f"- {product}: {amount:.2f}/{target:.2f} m³")

    def _print_final_status(self):
        """Print final simulation results"""
        print(f"\n=== Simulation Complete (Time: {self.env.now}) ===")
        print("Final Production Status:")
        
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