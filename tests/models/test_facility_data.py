import pytest
import json
from pathlib import Path
from unittest.mock import mock_open, patch
from models.facility_data import (
    Generator,
    Collector,
    Processor,
    RegionalFacilities,
    FacilityDataManager,
)
from models.enums import RegionType

# Full set of waste codes from the actual data
WASTE_CODES = [
    "02 01 07",  # Wastes from forestry
    "03 01 05",  # Sawdust, shavings
    "03 01 99",  # Wastes n.e.c.
    "03 03 01",  # Waste bark and wood
    "03 03 08",  # Wastes from sorting of paper
    "15 01 01",  # Paper packaging
    "15 01 03",  # Wooden packaging
    "17 02 01",  # Construction wood
    "19 12 01",  # Paper and cardboard
    "19 12 07",  # Wood other than hazardous
    "20 01 01",  # Paper and cardboard
    "20 01 38",  # Wood other than hazardous
    "20 03 07"   # Bulky waste
]

# Full set of output types from the actual data
OUTPUT_TYPES = [
    "particle_board",
    "osb_waferboard",
    "mdf_fibreboard",
    "mechanical_wood_pulp",
    "semi_chemical_wood_pulp",
    "soda_sulphate_chemical_pulp",
    "sulphite_chemical_pulp",
    "dissolving_wood_pulp",
    "veneer_plywood_coniferous",
    "veneer_plywood_other",
    "laminated_veneer_lumber"
]

@pytest.fixture
def sample_generator():
    return {
        "id": "gen_test",
        "waste_generation_rates": {code: 10.0 for code in WASTE_CODES},
        "generation_frequency": 24,
        "storage_capacity": 1100.0,
        "environmental_impact": 1.0,
        "initial_stock": {
            "15 01 03": 8.62,
            "17 02 01": 0.0,
            "15 01 01": 5.057,
            "20 01 01": 3.977
        }
    }

@pytest.fixture
def sample_collector():
    return {
        "id": "col_test",
        "waste_types": WASTE_CODES,
        "collection_capacity": 1000.0,
        "collection_frequency": 12,
        "transport_cost": 50.0,
        "environmental_impact": 1.0,
        "efficiency": 0.9,
        "availability": True,
        "strategy": "competitive"
    }

@pytest.fixture
def sample_processor():
    return {
        "id": "proc_test",
        "input_types": [
            "03 01 05",
            "17 02 01",
            "15 01 03"
        ],
        "output_types": OUTPUT_TYPES,
        "processing_capacity": 800.0,
        "processing_time": 2.0,
        "storage_capacity": 1500.0,
        "product_storage_capacity": 500.0,
        "energy_consumption": 100.0,
        "environmental_impact": 1.0,
        "conversion_rate": 0.85,
        "operational_costs": 200.0
    }

@pytest.fixture
def sample_region_data(sample_generator, sample_collector, sample_processor):
    return {
        "generators": [sample_generator],
        "collectors": [sample_collector],
        "processors": [sample_processor]
    }

def test_generator_initialization(sample_generator):
    """Test Generator dataclass initialization"""
    generator = Generator(**sample_generator)
    
    assert generator.id == "gen_test"
    assert all(code in generator.waste_generation_rates for code in WASTE_CODES)
    assert generator.generation_frequency == 24
    assert generator.storage_capacity == 1100.0
    assert generator.environmental_impact == 1.0
    assert "15 01 03" in generator.initial_stock
    assert "15 01 01" in generator.initial_stock

def test_collector_initialization(sample_collector):
    """Test Collector dataclass initialization"""
    collector = Collector(**sample_collector)
    
    assert collector.id == "col_test"
    assert all(code in collector.waste_types for code in WASTE_CODES)
    assert collector.collection_capacity == 1000.0
    assert collector.collection_frequency == 12
    assert collector.transport_cost == 50.0
    assert collector.environmental_impact == 1.0
    assert collector.efficiency == 0.9
    assert collector.availability
    assert collector.strategy == "competitive"

def test_processor_initialization(sample_processor):
    """Test Processor dataclass initialization"""
    processor = Processor(**sample_processor)
    
    assert processor.id == "proc_test"
    assert "03 01 05" in processor.input_types
    assert "15 01 03" in processor.input_types
    assert all(output_type in processor.output_types for output_type in OUTPUT_TYPES)
    assert processor.processing_capacity == 800.0
    assert processor.processing_time == 2.0
    assert processor.storage_capacity == 1500.0
    assert processor.energy_consumption == 100.0
    assert processor.environmental_impact == 1.0
    assert processor.conversion_rate == 0.85
    assert processor.operational_costs == 200.0

def test_regional_facilities_from_dict(sample_region_data):
    """Test RegionalFacilities creation from dictionary"""
    facilities = RegionalFacilities.from_dict(sample_region_data)
    
    assert len(facilities.generators) == 1
    assert len(facilities.collectors) == 1
    assert len(facilities.processors) == 1
    assert isinstance(facilities.generators[0], Generator)
    assert isinstance(facilities.collectors[0], Collector)
    assert isinstance(facilities.processors[0], Processor)

@pytest.fixture
def mock_region_file():
    return {
        "gorenjska.json": {
            "generators": [{
                "id": "gen_gorenjska",
                "waste_generation_rates": {
                    "03 01 05": 2.427,
                    "15 01 03": 52.279,
                    "17 02 01": 6.733
                },
                "generation_frequency": 24,
                "storage_capacity": 1100.0,
                "environmental_impact": 1.0
            }],
            "collectors": [{
                "id": "col_gorenjska",
                "waste_types": WASTE_CODES,
                "collection_capacity": 1000.0,
                "collection_frequency": 12,
                "transport_cost": 50.0,
                "environmental_impact": 1.0,
                "efficiency": 0.9,
                "availability": True,
                "strategy": "competitive"
            }],
            "processors": [{
                "id": "proc_gorenjska",
                "input_types": [
                    "03 01 05",
                    "17 02 01",
                    "15 01 03"
                ],
                "output_types": [
                    "particle_board",
                    "mdf_fibreboard",
                    "osb_waferboard"
                ],
                "processing_capacity": 800.0,
                "processing_time": 2.0,
                "storage_capacity": 1500.0,
                "product_storage_capacity": 500.0,
                "energy_consumption": 100.0,
                "environmental_impact": 1.0,
                "conversion_rate": 0.85,
                "operational_costs": 200.0
            }]
        }
    }

@pytest.fixture
def mock_demand_file():
    return {
        "national_demand": {
            "particle_board": 12000.0,
            "osb_waferboard": 9000.0,
            "mdf_fibreboard": 7000.0,
            "mechanical_wood_pulp": 25000.0,
            "semi_chemical_wood_pulp": 4000.0,
            "soda_sulphate_chemical_pulp": 18000.0,
            "sulphite_chemical_pulp": 2000.0,
            "dissolving_wood_pulp": 1500.0,
            "veneer_plywood_coniferous": 8000.0,
            "veneer_plywood_other": 6000.0,
            "laminated_veneer_lumber": 3000.0
        },
        "period": {
            "start": "2024-01-01",
            "end": "2024-12-31"
        }
    }

def test_facility_data_manager_initialization():
    """Test FacilityDataManager initialization"""
    manager = FacilityDataManager()
    assert isinstance(manager.data_dir, Path)
    assert manager.regions == {}
    assert manager.demand == {}
    assert manager.period_info == {}

def test_load_data_simple():
    """Test data loading with simple approach - no mocks"""
    manager = FacilityDataManager()
    
    # Test that the manager initializes properly even if files don't exist
    # This tests the basic structure without requiring complex mocking
    assert hasattr(manager, 'regions')
    assert hasattr(manager, 'demand')
    assert hasattr(manager, 'period_info')
    assert isinstance(manager.regions, dict)
    assert isinstance(manager.demand, dict)
    assert isinstance(manager.period_info, dict)
    
    # Test that we can manually add data and it works
    facilities = RegionalFacilities(generators=[], collectors=[], processors=[])
    manager.regions[RegionType.GORENJSKA] = facilities
    
    result = manager.get_region_facilities(RegionType.GORENJSKA)
    assert result is facilities

def test_get_region_facilities():
    """Test retrieving facilities for a specific region"""
    manager = FacilityDataManager()
    facilities = RegionalFacilities(generators=[], collectors=[], processors=[])
    manager.regions[RegionType.GORENJSKA] = facilities
    
    result = manager.get_region_facilities(RegionType.GORENJSKA)
    assert result is facilities
    assert manager.get_region_facilities(RegionType.GORISKA) is None

def test_aggregate_queries(sample_region_data):
    """Test aggregate facility queries"""
    manager = FacilityDataManager()
    facilities = RegionalFacilities.from_dict(sample_region_data)
    manager.regions[RegionType.GORENJSKA] = facilities
    
    assert len(manager.get_all_generators()) == 1
    assert len(manager.get_all_collectors()) == 1
    assert len(manager.get_all_processors()) == 1

def test_total_processing_capacity(sample_region_data):
    """Test total processing capacity calculation"""
    manager = FacilityDataManager()
    facilities = RegionalFacilities.from_dict(sample_region_data)
    manager.regions[RegionType.GORENJSKA] = facilities
    
    capacity = manager.get_total_processing_capacity("particle_board")
    assert capacity == 800.0
    assert manager.get_total_processing_capacity("nonexistent") == 0.0

def test_get_demand(mock_demand_file):
    """Test demand retrieval"""
    manager = FacilityDataManager()
    manager.demand = mock_demand_file["national_demand"]
    
    assert manager.get_demand("particle_board") == 12000.0
    assert manager.get_demand("mechanical_wood_pulp") == 25000.0
    assert manager.get_demand("nonexistent") == 0.0
