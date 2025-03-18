import simpy
import traceback
import numpy as np
from typing import Dict
from config import (
    SIMULATION_DURATION,
    TIME_PERIOD,
    TOTAL_YEARS
)
from config.base_config import get_uncertainty_set
from models.state import SimulationState
from monitoring.monitor import WasteMonitor
from monitoring.system_monitor import monitor_system
from models.facility_data import FacilityDataManager
from core.facility_builder import initialize_simulation_entities
from optimization.uncertainty import (
    ScenarioGenerator,
    UncertaintySet
)
from optimization.optimizer import WasteOptimizer
from optimization.objectives import (
    StorageUtilizationObjective,
    CollectionEfficiencyObjective,
    TreatmentEfficiencyObjective,
)
from optimization.strategies import OptimizationStrategy
from optimization.utils.simulation_tracker import SimulationTracker

class SimulationManager:
    """Manages simulation setup, execution, and monitoring"""
    
    def __init__(self):
        self.env = simpy.Environment()
        self.waste_monitor = WasteMonitor()
        self.state = SimulationState.get_instance()
        self.initial_params = {}
        self.optimizer = None
        self.scenario_generator = None
        self.tracker = SimulationTracker()
        
    def setup_optimization(self, scenario_name: str = "Baseline") -> None:
        """Set up optimization components"""
        # Get uncertainty set for specified scenario
        uncertainty_set = get_uncertainty_set(scenario_name)
        
        # Create scenario generator with proper uncertainty set
        self.scenario_generator = ScenarioGenerator(uncertainty_set)

        # Create objectives with simplified risk-aware evaluation
        objectives = [
            StorageUtilizationObjective(
                weight=0.35, should_minimize=True, risk_aversion=0.3
            ),
            CollectionEfficiencyObjective(
                weight=0.35, should_minimize=False, risk_aversion=0.3
            ),
            TreatmentEfficiencyObjective(
                weight=0.30, should_minimize=False, risk_aversion=0.3
            ),
        ]

        # Set scenario generator for each objective
        for objective in objectives:
            objective.set_scenario_generator(self.scenario_generator)

        # Create strategy with higher threshold for robustness
        strategy = OptimizationStrategy(threshold=0.4)

        # Create optimizer with objectives and strategy
        self.optimizer = WasteOptimizer(
            objectives=objectives,
            strategy=strategy,
            min_improvement_threshold=0.7
        )
        
        # Add metadata to tracker
        self.tracker.add_metadata(
            description=f"Simulation with {scenario_name} scenario",
            tags=[scenario_name, "stochastic_optimization"]
        )

    def initialize_entities(self, uncertainty_set: UncertaintySet) -> None:
        """Initialize simulation entities"""
        try:
            generators, collectors, operators = initialize_simulation_entities(
                self.env,
                uncertainty_set,
                self.waste_monitor.data_collector
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
        
        # Record initial state in tracker
        self._record_simulation_state()

    def _record_simulation_state(self) -> None:
        """Record current simulation state in tracker"""
        collection_rates = {
            c.name: c.collection_frequency for c in self.state.collectors
        }
        processing_rates = {
            t.name: t.processing_time for t in self.state.treatment_operators
        }
        storage_levels = {
            **{g.name: g.current_storage for g in self.state.generators},
            **{t.name: t.current_storage for t in self.state.treatment_operators}
        }
        
        # Get latest optimization results if available
        objective_scores = {}
        if hasattr(self.optimizer, 'last_result'):
            objective_scores = self.optimizer.last_result.scores
            
        # Calculate current metrics
        metrics = self._calculate_current_metrics()
        
        self.tracker.add_snapshot(
            timestamp=self.env.now,
            collection_rates=collection_rates,
            processing_rates=processing_rates,
            storage_levels=storage_levels,
            objective_scores=objective_scores,
            metrics=metrics
        )

    def _calculate_current_metrics(self) -> Dict[str, float]:
        """Calculate current performance metrics"""
        metrics = {
            "total_collected": sum(
                sum(c.collected_waste.values())
                for c in self.state.collectors
            ),
            "total_processed": sum(
                sum(t.processed_volumes.values())
                for t in self.state.treatment_operators
            ),
            "average_utilization": np.mean([
                t.current_storage / t.storage_capacity
                for t in self.state.treatment_operators
                if t.storage_capacity > 0
            ]) if self.state.treatment_operators else 0.0
        }
        return metrics

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
            monitor_system(
                self.env,
                self.waste_monitor,
                self.state.generators,
                self.state.collectors,
                self.state.treatment_operators,
            )
        )
        self.env.process(self._optimization_process())
        self.env.process(self._check_demand_satisfaction())
        self.env.process(self._state_tracking_process())

    def _state_tracking_process(self):
        """Process to periodically record simulation state"""
        while True:
            self._record_simulation_state()
            yield self.env.timeout(10)  # Record every 10 time units

    def _optimization_process(self):
        """Run periodic optimization of the system"""
        current_year = 1
        last_optimization_time = -25
        
        while True:
            if self.env.now >= last_optimization_time + 25:
                # Check for year transition and update parameters
                current_year = self._handle_year_transition(current_year)
                
                # Run optimization and print results
                result = self.optimizer.optimize()
                self._print_optimization_results(result)
                
                last_optimization_time = self.env.now
            
            yield self.env.timeout(1)

    def _handle_year_transition(self, current_year: int) -> int:
        """Handle year transition and parameter adjustments"""
        if self.env.now > 0 and self.env.now % TIME_PERIOD == 0:
            current_year = (self.env.now // TIME_PERIOD) + 1
            if current_year <= TOTAL_YEARS:
                print(f"\n=== Starting Year {current_year} at time {self.env.now} ===")
                self.scenario_generator.adjust_parameters(
                    waste_generation_multiplier=1.0 + (0.1 * (current_year - 1)),
                    efficiency_multiplier=1.0 + (0.05 * (current_year - 1)),
                )
        return current_year

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
        print(
            f"Using stochastic optimization with {self.scenario_generator.num_scenarios} scenarios"
        )
        self.env.run(until=SIMULATION_DURATION)
        self._print_final_status()
        
        # Save simulation history
        self.tracker.save_history("results/simulation_history.json")

    def _print_optimization_results(self, result):
        """Print detailed optimization results"""
        print(f"\n=== Optimization Results at Time {self.env.now} ===")
        print("Objective Scores (with risk measures):")
        for objective, score in result.scores.items():
            risk_measure = getattr(result, "risk_measures", {}).get(objective, 0.0)
            scenarios = getattr(result, "scenarios_evaluated", {}).get(objective, 1)
            print(f"- {objective}:")
            print(f"  Score: {score:.3f}")
            print(f"  Risk Measure (VaR): {risk_measure:.3f}")
            print(f"  Scenarios Evaluated: {scenarios}")

        if result.actions:
            print("\nOptimization Actions:")
            for action in result.actions:
                confidence = getattr(action, "confidence", 1.0)
                print(
                    f"- {action.entity_type}: {action.parameter} adjusted by {action.adjustment}"
                    f" (Confidence: {confidence:.2f})"
                )

        if result.suggestions:
            print("\nRobustness Suggestions:")
            for suggestion in result.suggestions:
                print(f"- {suggestion}")

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
            
        # Get simulation summary from tracker
        summary = self.tracker.get_summary()
        print("\nSimulation Summary:")
        print(f"Duration: {summary['duration']} time units")
        print(f"Number of snapshots: {summary['num_snapshots']}")
        print("\nFinal Metrics:")
        for metric, value in summary['final_metrics'].items():
            print(f"- {metric}: {value:.2f}")

    def create_visualizations(self):
        """Create visualization plots"""
        self.waste_monitor.plot_temporal_analysis(SIMULATION_DURATION)
