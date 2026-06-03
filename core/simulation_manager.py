import math
import simpy
import traceback
from typing import List, Dict, Any
from config.base_config import (
    ScenarioConfig
)
from config.constants import (
    SIMULATION_DURATION,
    SEASONAL_PERIODS,
    SEASONAL_AMPLITUDE,
    WEEKS_PER_YEAR,
    CONSUMPTION_INTERVAL_DAYS,
)
from core.transport_manager import PointToPointTransport
from models.data_classes import OperationalEntity
from models.enums import RegionType, OutputType, InventoryPolicy
from models.state import SimulationState
from monitoring.waste_monitor import WasteMonitor
from monitoring.mass_balance import EntityRegistry, MassBalanceMonitor
from models.facility_data import FacilityDataManager
from core import facility_builder as facility_builder_module
from core.facility_builder import FacilityBuilder
from core.kanban_manager import KanbanManager
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator

class SimulationManager:
    """Manages complete simulation lifecycle - setup, execution, and monitoring"""
    
    def __init__(self, seed=None):
        # Reset cross-run registries. The global state singleton is gone -- each
        # run owns an independent SimulationState injected downstream -- but the
        # OperationalEntity registries and the facility counters are still
        # process-global and must be cleared per run.
        OperationalEntity._entity_registry.clear()
        OperationalEntity._failure_counts.clear()
        facility_builder_module.facilities = {
            'WasteGenerator': 0,
            'CollectorCompany': 0,
            'TreatmentOperator': 0
        }

        self.seed = seed

        # Simulation state -- one fresh instance per run, injected into the
        # transport manager, facility builder, and every entity it builds.
        self.state = SimulationState()

        # Core simulation components
        self.env = simpy.Environment()
        self.waste_monitor = WasteMonitor(self.env)
        self.transport_manager = PointToPointTransport(state=self.state)

        # Kanban
        self.kanban_manager = KanbanManager()

        # Data and building components
        self.facility_manager = FacilityDataManager()
        self.facility_builder = None
        
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
                kanban_manager=self.kanban_manager,
                state=self.state,
                seed=self.seed
            )
            
            # Build all facilities
            generators, collectors, processors = self._build_all_facilities(scenario_config)

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

        # Total processing capacity across all regions, used to apportion each
        # operator's market share of national demand (ADR 0002). Computed up
        # front so market_share can be set at construction without disturbing
        # the per-entity seed-spawn order.
        total_processor_capacity = self._total_processor_capacity()

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
                market_share = (
                    proc_data.waste_storage_capacity / total_processor_capacity
                    if total_processor_capacity > 0
                    else 0.0
                )
                processor = self.facility_builder.create_processor(
                    proc_data, region, scenario_config.stock_strategy,
                    scenario_config.inventory_policy, market_share=market_share
                )
                processors.append(processor)

        return generators, collectors, processors

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
        # Start monitoring process
        self.env.process(
            self.waste_monitor.monitor_system_process(
                self.state.generators,
                self.state.collectors,
                self.state.treatment_operators,
            )
        )

        # Start weekly market consumption of finished goods
        self.env.process(self._market_consumption_process())

        # Mass-balance safety net (ADR 0002, Phase E.5). Construct now, at t=0,
        # so the snapshot captures the primed finished-goods inventory. Start
        # the check process AFTER market consumption so same-tick events fire
        # in insertion order -- the check runs once consumption has settled.
        self.mass_balance_monitor = MassBalanceMonitor(
            EntityRegistry(
                state=self.state,
                operators=self.state.treatment_operators,
                generators=self.state.generators,
                collectors=self.state.collectors,
            ),
            raise_on_violation=raise_on_violation,
        )
        self.env.process(self._mass_balance_check_process())

    def _mass_balance_check_process(self):
        """Check the product mass-balance invariant every consumption tick.

        Ticks on the same CONSUMPTION_INTERVAL_DAYS cadence as market
        consumption; because this process is started after the consumption
        process, its same-time event fires afterwards, so the check sees the
        inventory state once the tick's consumption has settled.
        """
        while True:
            yield self.env.timeout(CONSUMPTION_INTERVAL_DAYS)
            self.mass_balance_monitor.check_continuous(self.env.now)

    def run_simulation(self) -> None:
        """Execute the simulation"""
        print(f"Starting simulation for {SIMULATION_DURATION} time units...")
        self.env.run(until=SIMULATION_DURATION)
        self.mass_balance_monitor.check_final(self.env.now)
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
            # Raw run logs for post-hoc analysis (e.g. throughput bullwhip,
            # ADR 0004). Not persisted to the per-run KPI JSON; consumed in
            # process by extract_kpis.
            'transport_flows': self.state.transport_flows,
            'consumption_events': self.state.consumption_events,
            'final_summary': {
                'simulation_time': self.env.now,
                # Continuous market-consumption metrics (ADR 0002) -- the sole
                # service-level surface now that the demand ceiling is retired.
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
        }

    def _seasonal_factor(self, current_time: float) -> float:
        """Seasonal demand multiplier, aligned with waste-generation seasonality.

        Uses the same quarter-discretized sinusoid as WasteGenerator (see
        core/generator.py) so consumption and generation share one seasonal
        rhythm: SEASONAL_PERIODS periods over the run, amplitude
        SEASONAL_AMPLITUDE about a unit mean.
        """
        season_index = min(
            SEASONAL_PERIODS - 1,
            int(current_time / (SIMULATION_DURATION / SEASONAL_PERIODS))
        )
        return 1 + SEASONAL_AMPLITUDE * math.sin(2 * math.pi * season_index / SEASONAL_PERIODS)

    def _market_consumption_process(self):
        """Weekly market consumption of finished goods (ADR 0002).

        Models national demand as continuous market consumption rather than a
        production ceiling. Every CONSUMPTION_INTERVAL_DAYS, for each treatment
        operator and each product, the market attempts to consume
        ``market_share * (annual_demand[product] / WEEKS_PER_YEAR) *
        seasonal_factor`` from the operator's finished-goods inventory. The
        attempt is presented to every operator for every product, uniform
        across product types: an operator that cannot produce a product records
        the whole attempt as ``no_capability`` lost sales, while a capable
        operator with insufficient inventory records the shortfall as
        ``stockout`` lost sales. Every attempt is logged via
        ``SimulationState.record_consumption_event`` for service-level
        accounting.

        PULL operators additionally receive a market kanban signal carrying
        their total producible attempted volume -- the upstream-cascade trigger
        consumed by the PULL refactor (ADR 0002, Phase E). The signal carries
        ``attempted`` (not ``consumed``) so an emptied inventory does not
        starve future production.
        """
        national_demand = self.facility_manager.demand
        while True:
            yield self.env.timeout(CONSUMPTION_INTERVAL_DAYS)
            current_time = self.env.now
            seasonal_factor = self._seasonal_factor(current_time)

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
                        * seasonal_factor
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

                if (operator.inventory_policy == InventoryPolicy.PULL
                        and producible_attempted > 0):
                    self.kanban_manager.add_signal(
                        waste_type=None,
                        timestamp=current_time,
                        volume=producible_attempted,
                        source_id=operator.name,
                        source_type="market",
                    )

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