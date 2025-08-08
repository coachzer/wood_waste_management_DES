from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType
from models.data_classes import OperationalEntity, WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from monitoring.waste_monitor import WasteMonitor
from utils.unit_conversion import convert_generation_rates_to_volume

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
        kanban_manager=None
    ):
        self.env = env
        self.facility_manager = facility_manager
        self.waste_monitor = waste_monitor
        self.uncertainty_set = uncertainty_set
        self.transport_manager = transport_manager
        self.kanban_manager = kanban_manager

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
            kanban_manager=self.kanban_manager,
            failure_config=self.uncertainty_set.generator_failure if self.uncertainty_set else None
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

        # count this collector
        facilities['CollectorCompany'] += 1

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
            transport_manager=self.transport_manager,
            kanban_manager=self.kanban_manager,
            failure_config=self.uncertainty_set.collector_failure if self.uncertainty_set else None
        )

    def create_processor(self, proc_data, region: RegionType, stock_strategy=None, inventory_policy=None) -> TreatmentOperator:
        """Create a single treatment processor"""
        transformations = self._build_transformations(proc_data)
        product_storage_capacity = getattr(proc_data, "product_storage_capacity", proc_data.waste_storage_capacity)
        product_to_sell_capacity = getattr(proc_data, "product_to_sell_capacity", product_storage_capacity)

        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy

        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for processor {proc_data.id}")
        
        if inventory_policy is None and hasattr(self.uncertainty_set, 'inventory_policy'):
            inventory_policy = self.uncertainty_set.inventory_policy

        if inventory_policy is None:
            raise SystemExit(f"Error: No inventory policy specified for processor {proc_data.id}")
        
        # count this processor
        facilities['TreatmentOperator'] += 1

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
            product_storage_capacity=product_storage_capacity,
            product_to_sell_capacity=product_to_sell_capacity,
            scenario_config=self.uncertainty_set,
            stock_strategy=stock_strategy,
            inventory_policy=inventory_policy,
            transport_manager=self.transport_manager,
            kanban_manager=self.kanban_manager,
            failure_config=self.uncertainty_set.treatment_failure if self.uncertainty_set else None
        )

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