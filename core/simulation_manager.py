import simpy
import traceback
from typing import List, Dict, Any
from config.base_config import (
    ScenarioConfig
)
from config.constants import (
    SIMULATION_DURATION,
    WEEKS_PER_YEAR,
    CONSUMPTION_INTERVAL_DAYS,
)
from utils.seasonality import seasonal_factor
from core.transport_manager import PointToPointTransport
from models.enums import RegionType, OutputType, InventoryPolicy, StockStrategy, WasteType, sorted_by_value
from instrumentation.history_store import HISTORY_KEYS
from models.state import SimulationState
from instrumentation.waste_monitor import WasteMonitor
from instrumentation.mass_balance import EntityRegistry, MassBalanceMonitor
from models.facility_data import FacilityDataManager
from core.abc_analysis import abc_priority_weights
from core.facility_builder import FacilityBuilder
from core.kanban_manager import KanbanManager
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator

class SimulationManager:
    """Manages complete simulation lifecycle - setup, execution, and monitoring"""
    
    def __init__(self, seed=None):
        self.seed = seed

        self.state = SimulationState()

        self.env = simpy.Environment()
        self.waste_monitor = WasteMonitor(self.env)

        self.kanban_manager = KanbanManager()

        self.facility_manager = FacilityDataManager()
        self.facility_builder = None
        
    def initialize_entities(
        self,
        scenario_config: ScenarioConfig,
        inventory_policy: InventoryPolicy,
        stock_strategy: StockStrategy,
    ) -> None:
        """Single point of entity initialization and setup.

        The scenario config defines the operating environment only; the
        policy/strategy combo is the experimental grid axis, passed separately.
        """
        try:
            self.facility_manager.load_data()
            
            self.transport_manager = PointToPointTransport(
                state=self.state,
                road_circuity_mean=scenario_config.transportation_time[0],
            )

            self.facility_builder = FacilityBuilder(
                env=self.env,
                facility_manager=self.facility_manager,
                waste_monitor=self.waste_monitor,
                scenario=scenario_config,
                transport_manager=self.transport_manager,
                kanban_manager=self.kanban_manager,
                state=self.state,
                seed=self.seed,
                abc_priority_map=abc_priority_weights(self.facility_manager.demand),
            )
            
            generators, collectors, processors = self._build_all_facilities(
                inventory_policy, stock_strategy
            )

            self.state.initialize(generators, collectors, processors)
            
            print("Initialized simulation with:")
            print(f"  - {len(generators)} generators")
            print(f"  - {len(collectors)} collectors") 
            print(f"  - {len(processors)} processors")

        except ValueError as e:
            self._handle_initialization_error(e)

    def _build_all_facilities(
        self,
        inventory_policy: InventoryPolicy,
        stock_strategy: StockStrategy,
    ) -> tuple[List[WasteGenerator], List[CollectorCompany], List[TreatmentOperator]]:
        """Build all facilities for all regions using the facility builder"""
        generators = []
        collectors = []
        processors = []

        total_processor_capacity = self._total_processor_capacity()
        accepted_waste_types = self._nationally_accepted_waste_types()

        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if not facilities:
                continue
                
            for gen_data in facilities.generators:
                generator = self.facility_builder.create_generator(
                    gen_data, region, stock_strategy, inventory_policy,
                    accepted_waste_types=accepted_waste_types,
                )
                generators.append(generator)

            for col_data in facilities.collectors:
                collector = self.facility_builder.create_collector(
                    col_data, region, stock_strategy, inventory_policy
                )
                collectors.append(collector)

            for proc_data in facilities.processors:
                market_share = (
                    proc_data.waste_storage_capacity / total_processor_capacity
                    if total_processor_capacity > 0
                    else 0.0
                )
                processor = self.facility_builder.create_processor(
                    proc_data, region, stock_strategy, inventory_policy,
                    market_share=market_share
                )
                processors.append(processor)

        return generators, collectors, processors

    def _nationally_accepted_waste_types(self) -> List[WasteType]:
        """Waste types at least one processor in the country accepts. Generators send every
        other type to the outlet (ADR 0036)."""
        accepted = set()
        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if facilities:
                for proc_data in facilities.processors:
                    accepted.update(proc_data.input_types)
        return sorted_by_value(accepted)

    def _total_processor_capacity(self) -> float:
        """Sum of waste storage capacity across every processor in every region.

        Processing capacity is a fixed fraction of waste storage capacity, so
        this ratio also apportions market share by processing capacity.
        """
        total = 0.0
        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if not facilities:
                continue
            for proc_data in facilities.processors:
                total += proc_data.waste_storage_capacity
        return total

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

    def setup_processes(self, raise_on_violation: bool = True) -> None:
        """Set up all simulation processes.

        ``raise_on_violation`` is forwarded to the mass-balance monitor: single
        runs raise on a broken invariant; batch Monte Carlo passes ``False`` so
        one bad seed warns and continues instead of aborting the batch.
        """
        self.env.process(
            self.waste_monitor.monitor_system_process(
                self.state.generators,
                self.state.collectors,
                self.state.treatment_operators,
            )
        )

        self.env.process(self._market_consumption_process())

        self.mass_balance_monitor = MassBalanceMonitor(
            EntityRegistry(
                state=self.state,
                operators=self.state.treatment_operators,
                generators=self.state.generators,
                collectors=self.state.collectors,
                history=self.waste_monitor.store,
            ),
            raise_on_violation=raise_on_violation,
        )
        self.env.process(self._mass_balance_check_process())

    def _mass_balance_check_process(self):
        """Check the product mass-balance invariant every consumption tick.

        Ticks on CONSUMPTION_INTERVAL_DAYS; started after the consumption process,
        so its same-time event fires afterwards and the check sees settled state.
        """
        while True:
            yield self.env.timeout(CONSUMPTION_INTERVAL_DAYS)
            self.mass_balance_monitor.check_continuous(self.env.now)

    def run_simulation(self) -> None:
        """Execute the simulation"""
        print(f"Starting simulation for {SIMULATION_DURATION} time units...")
        self.env.run(until=SIMULATION_DURATION)
        self.mass_balance_monitor.check_final(self.env.now)
        self.mass_balance_monitor.check_waste_system(self.env.now)
        self.mass_balance_monitor.check_collection_centers(self.env.now)
        self.mass_balance_monitor.check_yield_bridge(self.env.now)
        self.mass_balance_monitor.check_generators(self.env.now)
        self._print_final_status()

    def get_monitor_data(self) -> Dict[str, Any]:
        """Extract all relevant monitoring data"""
        monitor_data: Dict[str, Any] = {
            key: getattr(self.waste_monitor.store, f"get_{key}")
            for key in HISTORY_KEYS
        }
        monitor_data.update({
            'transport_flows': self.state.transport_flows,
            'consumption_events': self.state.consumption_events,
            'storage_capacities': {
                'generators': {
                    generator.name: generator.waste_storage_capacity
                    for generator in self.state.generators
                },
                'collectors': {
                    collector.name: collector.waste_storage_capacity
                    for collector in self.state.collectors
                },
            },
            'final_summary': {
                'simulation_time': self.env.now,
                'full_service_level': self.state.full_service_level,
                'operational_service_level': self.state.operational_service_level,
                'total_attempted_consumption': self.state.total_attempted_consumption,
                'total_consumed': self.state.total_consumed,
                'no_capability_lost': self.state.no_capability_lost,
                'stockout_lost': self.state.stockout_lost,
                'consumption_service_by_product': {
                    product: self.state.service_level(product=product, kind="full")
                    for product in self.facility_manager.demand
                },
            }
        })
        return monitor_data

    def _market_consumption_process(self):
        """Weekly market consumption of finished goods (ADR 0002).

        Models national demand as continuous **Market Consumption**, not a
        production ceiling. Every CONSUMPTION_INTERVAL_DAYS, for each operator and
        product, the market attempts ``market_share * (annual_demand[product] /
        WEEKS_PER_YEAR) * seasonal_factor`` from finished-goods inventory. An
        operator that cannot produce a product records the attempt as
        ``no_capability`` lost sales; a capable one short on inventory records the
        shortfall as ``stockout``. Every attempt is logged via
        ``record_consumption_event``.

        PULL operators additionally receive a market kanban signal (ADR 0002, Phase E).
        Their backlog replaces the ``consumed`` volume it references (ADR 0029).
        """
        national_demand = self.facility_manager.demand
        while True:
            yield self.env.timeout(CONSUMPTION_INTERVAL_DAYS)
            current_time = self.env.now
            current_seasonal_factor = seasonal_factor(current_time)

            for operator in self.state.treatment_operators:
                producible_outputs = {
                    transformation.output_type
                    for transformation in operator.transformations.values()
                }
                producible_attempted = 0.0

                for product, annual_demand in national_demand.items():
                    attempted = (
                        operator.market_share
                        * (annual_demand / WEEKS_PER_YEAR)
                        * current_seasonal_factor
                    )
                    if attempted <= 0:
                        continue

                    output_type = OutputType(product)
                    if output_type in producible_outputs:
                        inventory = operator.finished_goods.current_storage[output_type]
                        consumed = min(attempted, inventory)
                        operator.finished_goods.current_storage[output_type] -= consumed
                        reason = "stockout" if consumed < attempted else None
                        producible_attempted += attempted
                    else:
                        consumed = 0.0
                        reason = "no_capability"

                    self.state.record_consumption_event(
                        operator_name=operator.name,
                        product=product,
                        attempted=attempted,
                        consumed=consumed,
                        reason=reason,
                        timestamp=current_time,
                    )

                if (operator.inventory_policy.is_pull()
                        and producible_attempted > 0):
                    self.kanban_manager.add_signal(
                        waste_type=None,
                        timestamp=current_time,
                        volume=producible_attempted,
                        source_id=operator.name,
                        source_type="market",
                    )

    def print_failure_analysis(self):
        entities_by_type = {
            "WasteGenerator": self.state.generators,
            "CollectorCompany": self.state.collectors,
            "TreatmentOperator": self.state.treatment_operators,
        }
        print("\n=== FAILURE ANALYSIS ===")
        for entity_type, entities in entities_by_type.items():
            total_failures = sum(entity.failure_count for entity in entities)
            if total_failures == 0:
                continue
            print(f"{entity_type}:")
            print(f"  Total entities: {len(entities)}")
            print(f"  Total failures: {total_failures}")
            print(f"  Failures per entity: {total_failures / len(entities):.3f}")

    def _print_final_status(self):
        """Print final simulation results (continuous market-consumption model)."""
        print(f"\n=== Simulation Complete (Time: {self.env.now}) ===")
        full = self.state.full_service_level
        operational = self.state.operational_service_level
        full_str = f"{full * 100:.2f}%" if full is not None else "n/a"
        operational_str = (
            f"{operational * 100:.2f}%" if operational is not None else "n/a"
        )
        print(
            f"Service level -- full: {full_str}, operational: {operational_str} "
            f"(consumed {self.state.total_consumed:.2f} / "
            f"attempted {self.state.total_attempted_consumption:.2f} m³)"
        )