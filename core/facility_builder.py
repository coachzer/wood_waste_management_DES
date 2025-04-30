from typing import Dict, Tuple, List
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType, OutputType
from models.data_classes import WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from optimization.stochastic import UncertaintySet
from monitoring.data_collector import DataCollector

class FacilityBuilder:
    """Builder class to create simulation entities from facility data"""

    def __init__(
        self,
        env: Environment,
        facility_manager: FacilityDataManager,
        data_collector: DataCollector,
        uncertainty_set: UncertaintySet = None,
    ):
        self.env = env
        self.facility_manager = facility_manager
        self.data_collector = data_collector
        self.uncertainty_set = uncertainty_set

    def create_generator(self, gen_data, region: RegionType) -> WasteGenerator:
        """Create a WasteGenerator from facility data"""
        waste_streams = {
            WasteType(wtype): rate  # Convert string type to enum
            for wtype, rate in gen_data.waste_generation_rates.items()
        }

        # Convert string waste types to enums in initial_stock if provided
        initial_stock = None
        if gen_data.initial_stock:
            initial_stock = {
                WasteType(wtype): volume
                for wtype, volume in gen_data.initial_stock.items()
            }

        return WasteGenerator(
            env=self.env,
            name=gen_data.id,
            waste_streams=waste_streams,
            generation_frequency=gen_data.generation_frequency,
            storage_capacity=gen_data.storage_capacity,
            priority_level=gen_data.priority_level,
            environmental_impact=gen_data.environmental_impact,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            initial_stock=initial_stock,
            data_collector=self.data_collector,
        )

    def create_collector(self, col_data, region: RegionType) -> CollectorCompany:
        """Create a CollectorCompany from facility data"""
        return CollectorCompany(
            env=self.env,
            name=col_data.id,
            collection_capacity=col_data.collection_capacity,
            collection_frequency=col_data.collection_frequency,
            transport_cost=col_data.transport_cost,
            environmental_impact=col_data.environmental_impact,
            efficiency=col_data.efficiency,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
        )

    def _get_base_transformations(self):
        """Get base transformation parameters"""
        return {
            # Primary materials (best for furniture)
            WasteType.CONSTRUCTION_WOOD: (0.98, 0.90),   # High quality, high energy
            WasteType.WOOD_CUTTINGS: (0.92, 0.85),       # Good quality, high energy
            WasteType.WASTE_WOODEN_PACKAGING: (0.88, 0.95), # Good for furniture after processing
            
            # Secondary materials
            WasteType.SAWDUST: (0.95, 0.50),
            WasteType.BARK_WASTE: (0.85, 0.70),
            WasteType.MIXED_WOOD: (0.88, 0.60),
            WasteType.WASTE_PAPER_PACKAGING: (0.82, 0.65),
        }

    def _adjust_furniture_efficiency(self, waste_type: WasteType, proc_data) -> float:
        """Adjust efficiency for furniture production"""
        efficiency = proc_data.conversion_rate
        if waste_type == WasteType.CONSTRUCTION_WOOD:
            return efficiency * 1.2
        elif waste_type == WasteType.WOOD_CUTTINGS:
            return efficiency * 1.1
        return efficiency

    def _should_process_furniture(self, is_furniture_processor, waste_type, furniture_materials, output_waste_type):
        """Determine if we should process furniture based on processor type and waste type"""
        if output_waste_type != OutputType.WOODEN_FURNITURE:
            return True
            
        return is_furniture_processor and waste_type in furniture_materials

    def _create_transformation(self, waste_type, output_waste_type, efficiency, energy, proc_data):
        """Create a transformation object with appropriate efficiency"""
        if output_waste_type == OutputType.WOODEN_FURNITURE:
            efficiency = self._adjust_furniture_efficiency(waste_type, proc_data)
            
        return WasteTransformation(
            input_type=waste_type,
            output_type=output_waste_type,
            conversion_efficiency=efficiency,
            energy_required=energy,
        )

    def _build_transformations(self, proc_data):
        """Build waste transformations for a processor"""
        base_transformations = self._get_base_transformations()
        transformations = {}
        
        is_furniture_processor = "furniture" in proc_data.id.lower()
        furniture_materials = {
            WasteType.CONSTRUCTION_WOOD,
            WasteType.WOOD_CUTTINGS,
            WasteType.WASTE_WOODEN_PACKAGING
        }
        
        for input_type in proc_data.input_types:
            waste_type = WasteType(input_type)
            if waste_type not in base_transformations:
                continue

            efficiency, energy = base_transformations[waste_type]
            
            for output_type in proc_data.output_types:
                if output_type.lower() == waste_type.value.lower():
                    continue

                output_waste_type = OutputType(output_type)
                key = (waste_type, output_waste_type)

                if not self._should_process_furniture(is_furniture_processor, waste_type, 
                                                    furniture_materials, output_waste_type):
                    continue

                transformations[key] = self._create_transformation(
                    waste_type, output_waste_type, efficiency, energy, proc_data
                )
                
        return transformations

    def create_processor(self, proc_data, region: RegionType) -> TreatmentOperator:
        """Create a TreatmentOperator from facility data"""
        transformations = self._build_transformations(proc_data)

        return TreatmentOperator(
            env=self.env,
            name=proc_data.id,
            processing_time=proc_data.processing_time,
            storage_capacity=proc_data.storage_capacity,
            energy_consumption=proc_data.energy_consumption,
            environmental_impact=proc_data.environmental_impact,
            conversion_rate=proc_data.conversion_rate,
            operational_costs=proc_data.operational_costs,
            region=region.value,
            uncertainty_set=self.uncertainty_set,
            transformations=transformations,
            data_collector=self.data_collector,
        )

    def build_all_facilities(
        self,
    ) -> Tuple[List[WasteGenerator], List[CollectorCompany], List[TreatmentOperator]]:
        """Build all facilities from configuration data"""
        generators = []
        collectors = []
        processors = []

        for region in RegionType:
            facilities = self.facility_manager.get_region_facilities(region)
            if facilities:
                # Create generators
                for gen_data in facilities.generators:
                    generator = self.create_generator(gen_data, region)
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
    uncertainty_set: UncertaintySet = None,
    data_collector: DataCollector = None,
    distribution_mode: str = "balanced",
    priority_types: List[str] = None
) -> Tuple[List, List, List]:
    """Initialize all simulation entities from facility data
    
    Args:
        env: SimPy environment
        uncertainty_set: Optional uncertainty parameters
        data_collector: Optional data collector instance
        distribution_mode: Type of distribution strategy ("balanced" or "priority")
        priority_types: List of output types to prioritize when in priority mode
    """
    # Load facility data
    facility_manager = FacilityDataManager()
    facility_manager.load_data()
    
    # Use provided data collector or create new one if none provided
    if data_collector is None:
        data_collector = DataCollector()

    # Create builder and build facilities
    builder = FacilityBuilder(env, facility_manager, data_collector, uncertainty_set)
    generators, collectors, processors = builder.build_all_facilities()

    # Group processors by output type
    processor_by_output = {}
    for processor in processors:
        for transformation in processor.transformations.values():
            output_type_str = transformation.output_type.value
            if output_type_str not in processor_by_output:
                processor_by_output[output_type_str] = []
            processor_by_output[output_type_str].append(processor)
    
    national_demand = facility_manager.demand

    if distribution_mode == "priority":
        _distribute_with_priority(processor_by_output, national_demand, priority_types)
    else:  # balanced mode
        _distribute_balanced(processor_by_output, national_demand)

    return generators, collectors, processors

def _distribute_demand(product_type: str, total_demand: float, processors: List, is_priority: bool = False) -> None:
    """Helper function to distribute demand among processors"""
    if not processors:
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
    if not priority_types:
        priority_types = ['wooden_furniture']
    
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
