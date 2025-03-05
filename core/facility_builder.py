from typing import Tuple, List
from simpy import Environment
from models.facility_data import FacilityDataManager
from models.enums import RegionType, WasteType
from models.data_classes import WasteTransformation
from core.generator import WasteGenerator
from core.collector import CollectorCompany
from core.treatment import TreatmentOperator
from optimization.stochastic import UncertaintySet


class FacilityBuilder:
    """Builder class to create simulation entities from facility data"""

    def __init__(
        self,
        env: Environment,
        facility_manager: FacilityDataManager,
        uncertainty_set: UncertaintySet = None,
    ):
        self.env = env
        self.facility_manager = facility_manager
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
        )

    def create_processor(self, proc_data, region: RegionType) -> TreatmentOperator:
        """Create a TreatmentOperator from facility data"""
        # Base transformation parameters from TreatmentOperator's defaults
        base_transformations = {
            WasteType.SAWDUST: (0.95, 0.5),  # 95% efficiency, 0.5 kWh/kg
            WasteType.WOOD_CUTTINGS: (0.90, 0.8),
            WasteType.BARK: (0.85, 0.7),
            WasteType.CORK: (0.92, 0.6),
            WasteType.SOLID_WOOD: (0.98, 0.9),
            WasteType.PAPER_PACKAGING: (0.80, 0.4),
            WasteType.WOOD_PACKAGING: (0.88, 0.7),
            WasteType.MIXED_WOOD: (1.0, 0.3),
        }

        # Create WasteTransformation objects for each input type
        transformations = {}
        for input_type in proc_data.input_types:
            waste_type = WasteType(input_type)
            if waste_type not in base_transformations:
                continue

            efficiency, energy = base_transformations[waste_type]
            # Create transformation for each configured output type
            for output_type in proc_data.output_types:
                if output_type.lower() == waste_type.value.lower():
                    # Skip if input and output are the same
                    continue

                output_waste_type = WasteType(output_type)
                key = (waste_type, output_waste_type)
                # Only create transformation if it makes logical sense
                if output_type.lower() in [
                    "wood_packaging",
                    "paper_packaging",
                    "mixed_wood",
                ]:
                    transformations[key] = WasteTransformation(
                        input_type=waste_type,
                        output_type=output_waste_type,
                        conversion_efficiency=efficiency,
                        energy_required=energy,
                    )

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
    env: Environment, uncertainty_set: UncertaintySet = None
) -> Tuple[List, List, List]:
    """Initialize all simulation entities from facility data"""
    # Load facility data
    facility_manager = FacilityDataManager()
    facility_manager.load_data()

    # Create builder and build facilities
    builder = FacilityBuilder(env, facility_manager, uncertainty_set)
    generators, collectors, processors = builder.build_all_facilities()

    # Distribute demand among treatment operators
    national_demand = facility_manager.demand
    processor_by_output = {}
    # First, group processors by output type
    for processor in processors:
        for output_type in processor.transformations.values():
            output_type_str = output_type.output_type.value
            if output_type_str not in processor_by_output:
                processor_by_output[output_type_str] = []
            processor_by_output[output_type_str].append(processor)

    # Then distribute demand among processors that can produce each type
    for product_type, total_demand in national_demand.items():
        if product_type in processor_by_output:
            processors_for_type = processor_by_output[product_type]
            # Distribute demand equally among processors that can produce this type
            demand_per_processor = total_demand / len(processors_for_type)
            for processor in processors_for_type:
                processor.demand = demand_per_processor

    return generators, collectors, processors
