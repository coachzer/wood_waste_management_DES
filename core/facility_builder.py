import numpy as np
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType, normalize_waste_type
from models.data_classes import WasteTransformation
from models.transformations import TRANSFORMATION_CATALOGUE, WASTE_TO_OUTPUT_TYPES
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from instrumentation.waste_monitor import WasteMonitor
from utils.unit_conversion import convert_generation_rates_to_volume
import math

from utils.seasonality import seasonal_factor_standard_deviation
from config.constants import (
    CONSUMPTION_INTERVAL_DAYS,
    OPERATING_TICK_DAYS,
    SAFETY_STOCK_Z,
    TREATMENT_REPLENISHMENT_LEAD_TIME_DAYS,
    WEEKS_PER_YEAR,
    FINISHED_GOODS_BUFFER_WEEKS,
    WASTE_STORAGE_PRIMING_WEEKS,
)
from utils.capacity_utils import per_tick_capacity

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
        self.facility_counts = {
            'WasteGenerator': 0,
            'CollectorCompany': 0,
            'TreatmentOperator': 0
        }

    def create_generator(self, gen_data, region: RegionType, stock_strategy=None, inventory_policy=None,
                         accepted_waste_types=None) -> WasteGenerator:
        """Create a single waste generator"""
        if gen_data.waste_storage_capacity <= 0:
            raise ValueError(f"Storage capacity must be positive, got {gen_data.waste_storage_capacity}")
        
        waste_streams = convert_generation_rates_to_volume(gen_data.waste_generation_rates)

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

        self.facility_counts['WasteGenerator'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return WasteGenerator(
            env=self.env,
            name=gen_data.id,
            waste_streams=waste_streams,
            generation_frequency=gen_data.generation_frequency,
            waste_storage_capacity=gen_data.waste_storage_capacity,
            efficiency=gen_data.efficiency,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            initial_stock=initial_stock,
            waste_monitor=self.waste_monitor,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
            kanban_manager=self.kanban_manager,
            state=self.state,
            failure_config=self.uncertainty_set.generator_failure if self.uncertainty_set else None,
            seed=child_seed,
            accepted_waste_types=accepted_waste_types,
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

        self.facility_counts['CollectorCompany'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return CollectorCompany(
            env=self.env,
            name=col_data.id,
            waste_types=waste_types_enum,
            collection_capacity=col_data.collection_capacity,
            collection_frequency=col_data.collection_frequency,
            vehicle_capacity=per_tick_capacity(
                col_data.collection_capacity, col_data.collection_frequency
            ),
            transport_cost=col_data.transport_cost,
            efficiency=col_data.efficiency,
            availability=col_data.availability,
            region=region.value,
            waste_monitor=self.waste_monitor,
            uncertainty_set=self.uncertainty_set,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
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
        order_share_by_waste_type = self._order_share_by_waste_type(transformations)
        order_up_to_level_m3 = self._order_up_to_level(
            transformations, market_share, proc_data.waste_storage_capacity
        )

        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy

        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for processor {proc_data.id}")
        
        if inventory_policy is None and hasattr(self.uncertainty_set, 'inventory_policy'):
            inventory_policy = self.uncertainty_set.inventory_policy

        if inventory_policy is None:
            raise SystemExit(f"Error: No inventory policy specified for processor {proc_data.id}")
        
        self.facility_counts['TreatmentOperator'] += 1
        [child_seed] = self.seed_sequence.spawn(1)

        return TreatmentOperator(
            env=self.env,
            name=proc_data.id,
            processing_time=proc_data.processing_time,
            waste_storage_capacity=proc_data.waste_storage_capacity,
            energy_consumption=proc_data.energy_consumption,
            environmental_impact=proc_data.environmental_impact,
            operational_costs=proc_data.operational_costs,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            transformations=transformations,
            waste_monitor=self.waste_monitor,
            finished_goods_capacity=finished_goods_capacity,
            initial_waste_storage=initial_waste_storage,
            order_share_by_waste_type=order_share_by_waste_type,
            order_up_to_level_m3=order_up_to_level_m3,
            market_share=market_share,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
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

    def _order_up_to_level(self, transformations, market_share: float, waste_storage_capacity: float) -> float:
        """Treatment order-up-to level S in waste m3 (ADR 0027), the same for PUSH and PULL.

        ``D`` is the waste needed per consumption interval to make this
        operator's share of producible demand, at the blended conversion
        efficiency. Demand arrives once per interval, so the protection period
        covers at least one whole interval. ``sigma`` is the seasonal spread
        of ``D``, the only demand variation in the model. Clamped at storage
        capacity.
        """
        if not transformations:
            return 0.0
        efficiencies = [transformation.conversion_efficiency for transformation in transformations.values()]
        blended_efficiency = sum(efficiencies) / len(efficiencies)
        national_demand = self.facility_manager.demand
        producible_products = sorted(
            {transformation.output_type.value for transformation in transformations.values()}
        )
        producible_annual_demand = sum(
            national_demand.get(product, 0.0) for product in producible_products
        )
        waste_per_interval = market_share * (producible_annual_demand / WEEKS_PER_YEAR) / blended_efficiency
        protection_intervals = max(
            1,
            math.ceil(
                (TREATMENT_REPLENISHMENT_LEAD_TIME_DAYS + OPERATING_TICK_DAYS) / CONSUMPTION_INTERVAL_DAYS
            ),
        )
        standard_deviation_per_interval = waste_per_interval * seasonal_factor_standard_deviation()
        order_up_to_level = (
            waste_per_interval * protection_intervals
            + SAFETY_STOCK_Z * standard_deviation_per_interval * math.sqrt(protection_intervals)
        )
        return min(waste_storage_capacity, order_up_to_level)

    def _order_share_by_waste_type(self, transformations) -> dict:
        """Each input type's share of the treatment order-up-to level (ADR 0026).

        Each producible product ``p`` needs ``demand_p / efficiency_p`` waste,
        with ``efficiency_p`` the mean efficiency of the routes to ``p``. That
        need is spread over the input types that can make ``p`` by the national
        generation mix (evenly if no region generates them). Collection crosses
        regions, so a type the home region lacks still gets ordered. A type's
        share is the sum of what it gets across products, so shares sum to 1.
        """
        national_demand = self.facility_manager.demand
        national_volume_by_type = {}
        for any_region in sorted(RegionType, key=lambda region_type: region_type.value):
            for waste_type, volume in self._region_generation_volume(any_region).items():
                national_volume_by_type[waste_type] = national_volume_by_type.get(waste_type, 0.0) + volume
        routes_by_product = {}
        for transformation in transformations.values():
            routes_by_product.setdefault(transformation.output_type, []).append(transformation)

        waste_need_by_product = {}
        for output_type in sorted(routes_by_product, key=lambda output_type: output_type.value):
            routes = routes_by_product[output_type]
            demand = national_demand.get(output_type.value, 0.0)
            mean_efficiency = sum(route.conversion_efficiency for route in routes) / len(routes)
            if demand > 0 and mean_efficiency > 0:
                waste_need_by_product[output_type] = demand / mean_efficiency
        total_need = sum(waste_need_by_product.values())
        if total_need <= 0:
            return {}

        share_by_waste_type = {}
        for output_type, need in waste_need_by_product.items():
            input_types = sorted(
                {route.input_type for route in routes_by_product[output_type]},
                key=lambda waste_type: waste_type.value,
            )
            weights = {waste_type: national_volume_by_type.get(waste_type, 0.0) for waste_type in input_types}
            total_weight = sum(weights.values())
            if total_weight <= 0:
                weights = {waste_type: 1.0 for waste_type in input_types}
                total_weight = float(len(input_types))
            for waste_type, weight in weights.items():
                share_by_waste_type[waste_type] = (
                    share_by_waste_type.get(waste_type, 0.0) + (need / total_need) * (weight / total_weight)
                )
        return {waste_type: share for waste_type, share in share_by_waste_type.items() if share > 0}

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

    def _build_transformations(self, proc_data):
        """Build waste transformation mappings for a processor"""
        transformations = {}

        for input_type in proc_data.input_types:
            waste_type = normalize_waste_type(input_type)
            if waste_type is None:
                print(f"Warning: Skipping invalid waste type: {input_type}")
                continue

            if waste_type not in TRANSFORMATION_CATALOGUE:
                continue

            efficiency, energy = TRANSFORMATION_CATALOGUE[waste_type]
            appropriate_outputs = [
                output_type.value
                for output_type in WASTE_TO_OUTPUT_TYPES.get(waste_type, [])
            ]
            
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
            count = self.facility_counts.get(entity_type, 0)
            if count > 0:
                rate = total_failures / count
                print(f"{entity_type}:")
                print(f"  Total entities: {count}")
                print(f"  Total failures: {total_failures}")
                print(f"  Failures per entity: {rate:.3f}")
            else:
                print(f"{entity_type}: No entities found")