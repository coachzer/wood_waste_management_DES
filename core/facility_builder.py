import numpy as np
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType
from models.data_classes import OperationalEntity, WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from core.strategies import build_stock_strategy, build_inventory_policy
from instrumentation.waste_monitor import WasteMonitor
from utils.unit_conversion import convert_generation_rates_to_volume
from config.constants import (
    WEEKS_PER_YEAR,
    FINISHED_GOODS_BUFFER_WEEKS,
    WASTE_STORAGE_PRIMING_WEEKS,
)

facilities = {
    'WasteGenerator': 0,
    'CollectorCompany': 0, 
    'TreatmentOperator': 0
}

class FacilityBuilder:
    """Focused on building individual facilities - no orchestration logic"""
    
    def __init__(
        self,
        env: Environment,
        facility_manager: FacilityDataManager,
        waste_monitor: WasteMonitor,
        uncertainty_set=None,
        transport_manager=None,
        kanban_manager=None,
        state=None,
        seed=None
    ):
        self.env = env
        self.facility_manager = facility_manager
        self.waste_monitor = waste_monitor
        self.uncertainty_set = uncertainty_set
        self.transport_manager = transport_manager
        self.kanban_manager = kanban_manager
        self.state = state
        self.seed_sequence = np.random.SeedSequence(seed)

    def create_generator(self, gen_data, region: RegionType, stock_strategy=None, inventory_policy=None) -> WasteGenerator:
        """Create a single waste generator"""
        if gen_data.waste_storage_capacity <= 0:
            raise ValueError(f"Storage capacity must be positive, got {gen_data.waste_storage_capacity}")
        
        waste_streams = convert_generation_rates_to_volume(gen_data.waste_generation_rates)

        # Convert initial stock from tonnes to m³ 
        initial_stock = None
        if gen_data.initial_stock:
            initial_stock_ewc = convert_generation_rates_to_volume(gen_data.initial_stock)
            initial_stock = initial_stock_ewc

        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy

            
        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for generator {gen_data.id}")

        if inventory_policy is None and hasattr(self.uncertainty_set, 'inventory_policy'):
            inventory_policy = self.uncertainty_set.inventory_policy

        if inventory_policy is None:
            raise SystemExit(f"Error: No inventory policy specified for generator {gen_data.id}")

        facilities['WasteGenerator'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return WasteGenerator(
            env=self.env,
            name=gen_data.id,
            waste_streams=waste_streams,
            generation_frequency=gen_data.generation_frequency,
            waste_storage_capacity=gen_data.waste_storage_capacity,
            environmental_impact=gen_data.environmental_impact,
            efficiency=gen_data.efficiency,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            initial_stock=initial_stock,
            waste_monitor=self.waste_monitor,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
            stock_strategy_behavior=build_stock_strategy(stock_strategy),
            inventory_policy_behavior=build_inventory_policy(inventory_policy),
            kanban_manager=self.kanban_manager,
            state=self.state,
            failure_config=self.uncertainty_set.generator_failure if self.uncertainty_set else None,
            seed=child_seed
        )

    def create_collector(self, col_data, region: RegionType, stock_strategy=None, inventory_policy=None) -> CollectorCompany:
        """Create a single collector company"""
        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy
            
        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for collector {col_data.id}")
        
        if inventory_policy is None and hasattr(self.uncertainty_set, 'inventory_policy'):
            inventory_policy = self.uncertainty_set.inventory_policy

        if inventory_policy is None:
            raise SystemExit(f"Error: No inventory policy specified for collector {col_data.id}")

        waste_types_enum = [WasteType(wtype) if not isinstance(wtype, WasteType) else wtype for wtype in col_data.waste_types]

        facilities['CollectorCompany'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return CollectorCompany(
            env=self.env,
            name=col_data.id,
            waste_types=waste_types_enum,
            collection_capacity=col_data.collection_capacity,
            collection_frequency=col_data.collection_frequency,
            transport_cost=col_data.transport_cost,
            environmental_impact=col_data.environmental_impact,
            efficiency=col_data.efficiency,
            availability=col_data.availability,
            region=region.value,
            waste_monitor=self.waste_monitor,
            uncertainty_set=self.uncertainty_set,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
            stock_strategy_behavior=build_stock_strategy(stock_strategy),
            inventory_policy_behavior=build_inventory_policy(inventory_policy),
            transport_manager=self.transport_manager,
            kanban_manager=self.kanban_manager,
            state=self.state,
            failure_config=self.uncertainty_set.collector_failure if self.uncertainty_set else None,
            seed=child_seed
        )

    def create_processor(self, proc_data, region: RegionType, stock_strategy=None, inventory_policy=None, market_share: float = 0.0) -> TreatmentOperator:
        """Create a single treatment processor.

        ``market_share`` is the operator's proportional share of national
        market demand (ADR 0002), computed by the caller from total processing
        capacity since a single processor cannot know the system-wide total.
        """
        transformations = self._build_transformations(proc_data)
        finished_goods_capacity = self._finished_goods_capacity(transformations, market_share)
        initial_waste_storage = self._prime_waste_storage(transformations, region, market_share)

        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy

        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for processor {proc_data.id}")
        
        if inventory_policy is None and hasattr(self.uncertainty_set, 'inventory_policy'):
            inventory_policy = self.uncertainty_set.inventory_policy

        if inventory_policy is None:
            raise SystemExit(f"Error: No inventory policy specified for processor {proc_data.id}")
        
        facilities['TreatmentOperator'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return TreatmentOperator(
            env=self.env,
            name=proc_data.id,
            processing_time=proc_data.processing_time,
            waste_storage_capacity=proc_data.waste_storage_capacity,
            energy_consumption=proc_data.energy_consumption,
            environmental_impact=proc_data.environmental_impact,
            conversion_rate=proc_data.conversion_rate,
            operational_costs=proc_data.operational_costs,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            transformations=transformations,
            waste_monitor=self.waste_monitor,
            finished_goods_capacity=finished_goods_capacity,
            initial_waste_storage=initial_waste_storage,
            market_share=market_share,
            scenario_config=self.uncertainty_set,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
            stock_strategy_behavior=build_stock_strategy(stock_strategy),
            inventory_policy_behavior=build_inventory_policy(inventory_policy),
            transport_manager=self.transport_manager,
            kanban_manager=self.kanban_manager,
            state=self.state,
            failure_config=self.uncertainty_set.treatment_failure if self.uncertainty_set else None,
            seed=child_seed
        )

    def _finished_goods_capacity(self, transformations, market_share: float) -> dict:
        """Per-product finished-goods capacity (ADR 0002, Phase C).

        ``capacity[product] = market_share * (annual_demand[product] /
        WEEKS_PER_YEAR) * buffer_weeks`` for every product the operator can
        actually produce. ``buffer_weeks`` is per-scenario (the bucket-C
        sensitivity sweep, default ``FINISHED_GOODS_BUFFER_WEEKS``).
        Non-producible products are omitted: the market records them as
        no-capability lost sales and never touches their inventory, so priming
        them would be meaningless dead stock.
        """
        buffer_weeks = getattr(
            self.uncertainty_set, "finished_goods_buffer_weeks", FINISHED_GOODS_BUFFER_WEEKS
        )
        national_demand = self.facility_manager.demand
        producible_outputs = sorted(
            {transformation.output_type for transformation in transformations.values()},
            key=lambda output_type: output_type.value,
        )
        return {
            output_type: (
                market_share
                * (national_demand[output_type.value] / WEEKS_PER_YEAR)
                * buffer_weeks
            )
            for output_type in producible_outputs
            if output_type.value in national_demand
        }

    def _prime_waste_storage(self, transformations, region: RegionType, market_share: float) -> dict:
        """Prime waste storage to ~2 weeks of producible throughput (ADR 0002, Phase C).

        The total primed volume is ``(annual_demand_total / WEEKS_PER_YEAR) *
        WASTE_STORAGE_PRIMING_WEEKS * market_share / blended_efficiency`` waste
        m3, distributed across the operator's accepted input waste types in
        proportion to the region's volume-generation mix. A type the region does
        not generate gets zero (it arrives later via collection); if the region
        generates none of the input types, an even split avoids divide-by-zero.
        ``blended_efficiency`` is the mean conversion efficiency across the
        operator's transformations -- this only shapes the warm-up mix, which
        collection self-corrects within ~2 weeks, so precision is irrelevant.
        """
        input_types = sorted(
            {transformation.input_type for transformation in transformations.values()},
            key=lambda waste_type: waste_type.value,
        )
        if not input_types:
            return {}

        efficiencies = [transformation.conversion_efficiency for transformation in transformations.values()]
        blended_efficiency = sum(efficiencies) / len(efficiencies)

        national_demand = self.facility_manager.demand
        annual_demand_total = sum(national_demand.values())
        total_prime = (
            (annual_demand_total / WEEKS_PER_YEAR)
            * WASTE_STORAGE_PRIMING_WEEKS
            * market_share
            / blended_efficiency
        )

        region_volume_by_type = self._region_generation_volume(region)
        weights = {waste_type: region_volume_by_type.get(waste_type, 0.0) for waste_type in input_types}
        total_weight = sum(weights.values())

        if total_weight <= 0:
            even_share = total_prime / len(input_types)
            return {waste_type: even_share for waste_type in input_types}

        return {
            waste_type: total_prime * weight / total_weight
            for waste_type, weight in weights.items()
        }

    def _region_generation_volume(self, region: RegionType) -> dict:
        """Sum each waste type's volume-generation rate across the region's generators.

        Generation rates live in tonnes; ``convert_generation_rates_to_volume``
        applies per-type densities so the priming split reflects how waste
        actually arrives (waste storage is measured in m3).
        """
        volume_by_type = {}
        facilities = self.facility_manager.get_region_facilities(region)
        if not facilities:
            return volume_by_type
        for generator in facilities.generators:
            for waste_type, volume in convert_generation_rates_to_volume(generator.waste_generation_rates).items():
                volume_by_type[waste_type] = volume_by_type.get(waste_type, 0.0) + volume
        return volume_by_type

    # Private helper methods for processor creation
    def _get_base_transformations(self):
        """Get base transformation efficiencies and energy requirements"""
        return {
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95),
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),
            WasteType.BARK_CORK_WASTE_03_01_01: (0.85, 0.70),
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),
            WasteType.FORESTRY_WASTE_02_01_07: (0.82, 0.75),
            WasteType.OTHER_WOOD_WASTE_03_01_99: (0.85, 0.65),
        }

    def _map_waste_type(self, input_type):
        """Map string waste type codes to WasteType enums"""
        waste_type_mapping = {
            "03_01_05": WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05,
            "15_01_03": WasteType.WOODEN_PACKAGING_15_01_03,
            "17_02_01": WasteType.CONSTRUCTION_WOOD_17_02_01,
            "03_01_01": WasteType.BARK_CORK_WASTE_03_01_01,
            "20_01_38": WasteType.NON_HAZARDOUS_WOOD_20_01_38,
            "15_01_01": WasteType.PAPER_PACKAGING_15_01_01
        }
        
        mapped_type = waste_type_mapping.get(input_type, input_type)
        return WasteType(mapped_type)
    
    def _get_appropriate_mappings(self):
        """Get appropriate output products for each waste type"""
        return {
            WasteType.CONSTRUCTION_WOOD_17_02_01: ['particle_board', 'osb'],
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: ['particle_board', 'mdf'],
            WasteType.WOODEN_PACKAGING_15_01_03: ['particle_board', 'osb'],
            WasteType.BARK_CORK_WASTE_03_01_01: ['mdf', 'particle_board'],
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: ['particle_board', 'mdf', 'osb'],
            WasteType.PAPER_PACKAGING_15_01_01: ['mdf'],
            WasteType.FORESTRY_WASTE_02_01_07: ['particle_board', 'mdf'],
            WasteType.OTHER_WOOD_WASTE_03_01_99: ['particle_board', 'mdf', 'osb'],
        }

    def _build_transformations(self, proc_data):
        """Build waste transformation mappings for a processor"""
        base_transformations = self._get_base_transformations()
        appropriate_mappings = self._get_appropriate_mappings()
        transformations = {}
                
        for input_type in proc_data.input_types:
            try:
                waste_type = self._map_waste_type(input_type)
            except ValueError:
                print(f"Warning: Skipping invalid waste type: {input_type}")
                continue

            if waste_type not in base_transformations:
                continue

            efficiency, energy = base_transformations[waste_type]
            appropriate_outputs = appropriate_mappings.get(waste_type, [])
            
            for output_type in proc_data.output_types:
                if output_type.lower() == waste_type.value.lower():
                    continue
                
                if output_type.lower() not in appropriate_outputs:
                    continue

                try:
                    output_waste_type = OutputType(output_type)
                except ValueError:
                    print(f"Warning: Skipping invalid output type: {output_type}")
                    continue
                    
                key = (waste_type, output_waste_type)
                transformations[key] = WasteTransformation(
                    input_type=waste_type,
                    output_type=output_waste_type,
                    conversion_efficiency=efficiency,
                    energy_required=energy,
                )
                
        return transformations
    
def print_failure_analysis():
    stats = OperationalEntity.get_failure_stats()
    print("\n=== FAILURE ANALYSIS ===")
    for entity_type, total_failures in stats.items():
        count = facilities.get(entity_type, 0)
        if count > 0:
            rate = total_failures / count
            print(f"{entity_type}:")
            print(f"  Total entities: {count}")
            print(f"  Total failures: {total_failures}")
            print(f"  Failures per entity: {rate:.3f}")
        else:
            print(f"{entity_type}: No entities found")