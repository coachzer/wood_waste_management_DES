from typing import Dict, Tuple, List
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType
from models.data_classes import WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from monitoring.data_collector import DataCollector

class FacilityBuilder:
    """Builder class to create simulation entities from facility data"""

    def __init__(
        self,
        env: Environment,
        facility_manager: FacilityDataManager,
        data_collector: DataCollector,
        uncertainty_set = None,
    ):
        self.env = env
        self.facility_manager = facility_manager
        self.data_collector = data_collector
        self.uncertainty_set = uncertainty_set

    def create_generator(self, gen_data, region: RegionType, stock_strategy=None) -> WasteGenerator:
        """Create a WasteGenerator from facility data, supporting scenario-specific stock_strategy"""
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

        # Ensure stock_strategy is properly passed from scenario config
        if stock_strategy is None and hasattr(self.uncertainty_set, 'stock_strategy'):
            stock_strategy = self.uncertainty_set.stock_strategy
            
        if stock_strategy is None:
            raise SystemExit(f"Error: No stock strategy specified for generator {gen_data.id}. "
                          "Must provide stock_strategy either through initialize_simulation_entities() or uncertainty_set")

        print(f"[DEBUG] Creating generator {gen_data.id} with strategy: {stock_strategy}")
        print(f"[DEBUG] Generator {gen_data.id} will use stock strategy: {stock_strategy}")
        # raise SystemExit("Debug print added - exiting to show strategy")

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
            data_collector=self.data_collector,
            stock_strategy=stock_strategy,
        )

    def create_collector(self, col_data, region: RegionType) -> CollectorCompany:
        """Create a CollectorCompany from facility data"""

        scenario_strategy = getattr(self.uncertainty_set, 'coordination_strategy', None)
        
        strategy = scenario_strategy if scenario_strategy is not None else getattr(col_data, 'strategy', 'competitive')

        # Convert waste_types to WasteType enums for correct matching
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
            strategy=strategy,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
        )

    def _get_base_transformations(self):
        """Get base transformation parameters"""
        return {
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),   
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95), 
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),
            WasteType.BARK_WASTE_03_01_01: (0.85, 0.70),
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),
        }

    def _adjust_furniture_efficiency(self, waste_type: WasteType, proc_data) -> float:
        """Adjust efficiency for furniture production"""
        efficiency = proc_data.conversion_rate
        if waste_type == WasteType.CONSTRUCTION_WOOD_17_02_01:
            return efficiency * 1.2
        return efficiency

    def _create_transformation(self, waste_type, output_waste_type, efficiency, energy):
        """Create a transformation object with appropriate efficiency"""
        return WasteTransformation(
            input_type=waste_type,
            output_type=output_waste_type,
            conversion_efficiency=efficiency,
            energy_required=energy,
        )

    def _map_waste_type(self, input_type):
        """Map invalid waste type strings to valid WasteType enum values"""
        # Handle non-standard waste types from JSON data
        waste_type_mapping = {
            "wood_cuttings": "03 01 05",  # Map to sawdust/shavings/cuttings
            "mixed_wood": "03 01 99",     # Map to other wood waste
        }
        
        # Use mapping if available, otherwise use original input_type
        mapped_type = waste_type_mapping.get(input_type, input_type)
        return WasteType(mapped_type)

    def _build_transformations(self, proc_data):
        """Build waste transformations for a processor"""
        base_transformations = self._get_base_transformations()
        transformations = {}
        
        # Define appropriate waste-to-product mappings
        appropriate_mappings = {
            WasteType.CONSTRUCTION_WOOD_17_02_01: ['particle_board', 'osb_waferboard'],
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: ['particle_board', 'mdf_fibreboard'],
            WasteType.WOODEN_PACKAGING_15_01_03: ['particle_board', 'osb_waferboard'],
            WasteType.BARK_WASTE_03_01_01: ['mdf_fibreboard', 'particle_board'],
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: ['particle_board', 'mdf_fibreboard', 'osb_waferboard'],
            WasteType.PAPER_PACKAGING_15_01_01: ['mdf_fibreboard'],
        }
                
        for input_type in proc_data.input_types:
            try:
                waste_type = self._map_waste_type(input_type)
            except ValueError:
                print(f"Warning: Skipping invalid waste type: {input_type}")
                continue

            if waste_type not in base_transformations:
                continue

            efficiency, energy = base_transformations[waste_type]
            
            # Only create transformations for appropriate waste-to-product combinations
            appropriate_outputs = appropriate_mappings.get(waste_type, [])
            
            for output_type in proc_data.output_types:
                if output_type.lower() == waste_type.value.lower():
                    continue
                
                # Skip if this waste type shouldn't produce this output type
                if output_type.lower() not in appropriate_outputs:
                    continue

                try:
                    output_waste_type = OutputType(output_type)
                except ValueError:
                    print(f"Warning: Skipping invalid output type: {output_type}")
                    continue
                    
                key = (waste_type, output_waste_type)

                transformations[key] = self._create_transformation(
                    waste_type, output_waste_type, efficiency, energy
                )
                
        return transformations

    def create_processor(self, proc_data, region: RegionType) -> TreatmentOperator:
        """Create a TreatmentOperator from facility data"""
        transformations = self._build_transformations(proc_data)

        # Use product_storage_capacity if present, else default to waste_storage_capacity
        product_storage_capacity = getattr(proc_data, "product_storage_capacity", proc_data.waste_storage_capacity)
        # New field: product_to_sell_capacity (capacity for products to sell before storing surplus)
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
            data_collector=self.data_collector,
            product_storage_capacity=product_storage_capacity,
            product_to_sell_capacity=product_to_sell_capacity,
        )

    def build_all_facilities(
        self,
        stock_strategy=None,
    ) -> Tuple[List[WasteGenerator], List[CollectorCompany], List[TreatmentOperator]]:
        """Build all facilities from configuration data, supporting scenario-specific stock_strategy"""
        generators = []
        collectors = []
        processors = []

        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if facilities:
                # Create generators
                for gen_data in facilities.generators:
                    generator = self.create_generator(gen_data, region, stock_strategy=stock_strategy)
                    generators.append(generator)

                # Create collectors
                for col_data in facilities.collectors:
                    collector = self.create_collector(col_data, region)
                    collectors.append(collector)

                # Create processors
                for proc_data in facilities.processors:
                    processor = self.create_processor(proc_data, region)
                    processors.append(processor)

        return generators, collectors, processors

def initialize_simulation_entities(
    env: Environment, 
    uncertainty_set = None,
    data_collector: DataCollector = None,
    distribution_mode: str = "balanced",
    priority_types: List[str] = None,
    stock_strategy=None,
) -> Tuple[List, List, List]:
    """Initialize all simulation entities from facility data, supporting scenario-specific stock_strategy
    
    Args:
        env: SimPy environment
        uncertainty_set: Optional uncertainty parameters
        data_collector: Optional data collector instance
        distribution_mode: Type of distribution strategy ("balanced" or "priority")
        priority_types: List of output types to prioritize when in priority mode
        stock_strategy: Scenario-specific stock strategy for generators
    """
    # Load facility data
    facility_manager = FacilityDataManager()
    facility_manager.load_data()
    
    # Use provided data collector or create new one if none provided
    if data_collector is None:
        data_collector = DataCollector()

    # Create builder and build facilities
    builder = FacilityBuilder(env, facility_manager, data_collector, uncertainty_set)
    generators, collectors, processors = builder.build_all_facilities(stock_strategy=stock_strategy)

    # Group processors by output type
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
    """Helper function to distribute demand among processors"""
    if not processors:
        print(f"No processors available for {product_type} demand distribution")
        return
    
    demand_per_processor = total_demand / len(processors)
    priority_tag = "(PRIORITY)" if is_priority else ""
    print(f"\nDistributing {product_type} demand {total_demand} among {len(processors)} processors {priority_tag}")
    for processor in processors:
        processor.demand = demand_per_processor
        print(f"Assigned {demand_per_processor:.2f} m³ {product_type} demand to {processor.name}")

def _get_valid_processors(product_type: str, processor_by_output: Dict) -> List:
    """Helper function to get valid processors for a product type"""
    processors = processor_by_output.get(product_type, [])
    if product_type == 'wooden_furniture':
        return [p for p in processors if 'furniture' in p.name.lower()]
    return processors

def _distribute_with_priority(processor_by_output: Dict, national_demand: Dict, priority_types: List[str]) -> None:
    """Distribute demand with priority given to specified types"""
    
    # Handle priority types first
    for product_type in priority_types:
        if product_type not in national_demand:
            continue
        
        processors = _get_valid_processors(product_type, processor_by_output)
        _distribute_demand(product_type, national_demand[product_type], processors, True)
    
    # Handle remaining types
    remaining_types = set(national_demand.keys()) - set(priority_types)
    for product_type in remaining_types:
        processors = _get_valid_processors(product_type, processor_by_output)
        _distribute_demand(product_type, national_demand[product_type], processors)

def _distribute_balanced(processor_by_output: Dict, national_demand: Dict) -> None:
    """Distribute demand evenly among all processors"""
    for product_type, total_demand in national_demand.items():
        if product_type not in processor_by_output:
            continue
            
        processors = processor_by_output[product_type]
        
        # For furniture, only use dedicated processors
        if product_type == 'wooden_furniture':
            processors = [p for p in processors if 'furniture' in p.name.lower()]
            
        if not processors:
            continue
            
        # Distribute demand equally
        demand_per_processor = total_demand / len(processors)
        print(f"\nDistributing {product_type} demand {total_demand} among {len(processors)} processors")
        for processor in processors:
            processor.demand = demand_per_processor
            print(f"Assigned {demand_per_processor:.2f} m³ {product_type} demand to {processor.name}")
