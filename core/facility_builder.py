from typing import Dict, Tuple, List
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType
from models.data_classes import WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from monitoring.waste_monitor import WasteMonitor

class FacilityBuilder:
    def __init__(
        self,
        env: Environment,
        facility_manager: FacilityDataManager,
        waste_monitor: WasteMonitor,
        uncertainty_set = None,
    ):
        self.env = env
        self.facility_manager = facility_manager
        self.waste_monitor = waste_monitor
        self.uncertainty_set = uncertainty_set

    def create_generator(self, gen_data, region: RegionType, stock_strategy=None) -> WasteGenerator:
        if gen_data.waste_storage_capacity <= 0:
            raise ValueError(f"Storage capacity must be positive, got {gen_data.waste_storage_capacity}")

        waste_streams = {
            WasteType(wtype): rate 
            for wtype, rate in gen_data.waste_generation_rates.items()
        }

        initial_stock = None
        if gen_data.initial_stock:
            initial_stock = {
                WasteType(wtype): volume
                for wtype, volume in gen_data.initial_stock.items()
            }

        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy
            
        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for generator {gen_data.id}")

        return WasteGenerator(
            env=self.env,
            name=gen_data.id,
            waste_streams=waste_streams,
            generation_frequency=gen_data.generation_frequency,
            waste_storage_capacity=gen_data.waste_storage_capacity,
            environmental_impact=gen_data.environmental_impact,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            initial_stock=initial_stock,
            waste_monitor=self.waste_monitor,
            stock_strategy=stock_strategy,
        )

    def create_collector(self, col_data, region: RegionType) -> CollectorCompany:

        waste_types_enum = [WasteType(wtype) if not isinstance(wtype, WasteType) else wtype for wtype in col_data.waste_types]
        
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
            uncertainty_set=self.uncertainty_set,
        )

    def _get_base_transformations(self):
        return {
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),   
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95), 
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),
            WasteType.BARK_WASTE_03_01_01: (0.85, 0.70),
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),
        }

    def _map_waste_type(self, input_type):
        waste_type_mapping = {
            "wood_cuttings": "03 01 05",
            "mixed_wood": "03 01 99",
        }
        
        mapped_type = waste_type_mapping.get(input_type, input_type)
        return WasteType(mapped_type)
    
    def _get_appropriate_mappings(self):
        return {
            WasteType.CONSTRUCTION_WOOD_17_02_01: ['particle_board', 'osb_waferboard'],
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: ['particle_board', 'mdf_fibreboard'],
            WasteType.WOODEN_PACKAGING_15_01_03: ['particle_board', 'osb_waferboard'],
            WasteType.BARK_WASTE_03_01_01: ['mdf_fibreboard', 'particle_board'],
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: ['particle_board', 'mdf_fibreboard', 'osb_waferboard'],
            WasteType.PAPER_PACKAGING_15_01_01: ['mdf_fibreboard'],
        }

    def _build_transformations(self, proc_data):
        base_transformations = self._get_base_transformations()
        transformations = {}
        
        appropriate_mappings = self._get_appropriate_mappings()
                
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

    def create_processor(self, proc_data, region: RegionType) -> TreatmentOperator:
        transformations = self._build_transformations(proc_data)
        product_storage_capacity = getattr(proc_data, "product_storage_capacity", proc_data.waste_storage_capacity)
        product_to_sell_capacity = getattr(proc_data, "product_to_sell_capacity", product_storage_capacity)

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
        )

    def build_all_facilities(self, stock_strategy=None) -> Tuple[List[WasteGenerator], List[CollectorCompany], List[TreatmentOperator]]:
        generators = []
        collectors = []
        processors = []

        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if facilities:
                for gen_data in facilities.generators:
                    generator = self.create_generator(gen_data, region, stock_strategy=stock_strategy)
                    generators.append(generator)

                for col_data in facilities.collectors:
                    collector = self.create_collector(col_data, region)
                    collectors.append(collector)

                for proc_data in facilities.processors:
                    processor = self.create_processor(proc_data, region)
                    processors.append(processor)

        return generators, collectors, processors

def initialize_simulation_entities(
    env: Environment, 
    uncertainty_set = None,
    waste_monitor: WasteMonitor = None,
    distribution_mode: str = "balanced",
    priority_types: List[str] = None,
    stock_strategy=None,
) -> Tuple[List, List, List]:
    facility_manager = FacilityDataManager()
    facility_manager.load_data()
    
    if waste_monitor is None:
        waste_monitor = WasteMonitor()

    builder = FacilityBuilder(env, facility_manager, waste_monitor, uncertainty_set)
    generators, collectors, processors = builder.build_all_facilities(stock_strategy=stock_strategy)

    processor_by_output = {}
    for processor in processors:
        for transformation in processor.transformations.values():
            output_type_str = transformation.output_type.value
            if output_type_str not in processor_by_output:
                processor_by_output[output_type_str] = []
            processor_by_output[output_type_str].append(processor)
    
    national_demand = facility_manager.demand

    match distribution_mode:
        case "priority":
            _distribute_with_priority(processor_by_output, national_demand, priority_types)
        case "balanced":
            _distribute_balanced(processor_by_output, national_demand)
        case _:
            raise ValueError(f"Unknown distribution_mode: {distribution_mode}")

    return generators, collectors, processors

def _distribute_demand(product_type: str, total_demand: float, processors: List, is_priority: bool = False) -> None:
    if not processors:
        print(f"No processors available for {product_type} demand distribution")
        return
    
    demand_per_processor = total_demand / len(processors)
    priority_tag = "(PRIORITY)" if is_priority else ""
    print(f"\nDistributing {product_type} demand {total_demand} among {len(processors)} processors {priority_tag}")
    for processor in processors:
        processor.demand = demand_per_processor
        print(f"Assigned {demand_per_processor:.2f} m³ {product_type} demand to {processor.name}")

def _distribute_with_priority(processor_by_output: Dict, national_demand: Dict, priority_types: List[str]) -> None:
    for product_type in priority_types:
        if product_type in national_demand:
            processors = processor_by_output.get(product_type, [])
            _distribute_demand(product_type, national_demand[product_type], processors, True)
    
    remaining_types = set(national_demand.keys()) - set(priority_types)
    for product_type in remaining_types:
        processors = processor_by_output.get(product_type, [])
        _distribute_demand(product_type, national_demand[product_type], processors)

def _distribute_balanced(processor_by_output: Dict, national_demand: Dict) -> None:
    for product_type, total_demand in national_demand.items():
        processors = processor_by_output.get(product_type, [])
        if processors:
            demand_per_processor = total_demand / len(processors)
            print(f"\nDistributing {product_type} demand {total_demand} among {len(processors)} processors")
            for processor in processors:
                processor.demand = demand_per_processor
                print(f"Assigned {demand_per_processor:.2f} m³ {product_type} demand to {processor.name}")