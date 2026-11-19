"""RegionalFacilities.from_dict turns region-JSON EWC strings into WasteType members."""
from models.entities import RegionalFacilities
from models.enums import OutputType, WasteType

REGION_DATA = {
    "generators": [{
        "id": "g",
        "waste_generation_rates": {"03 01 05": 2.0, "99 99 99": 1.0, "17 02 01": 3.0},
        "generation_frequency": 1.0,
        "waste_storage_capacity": 10.0,
        "efficiency": 1.0,
        "initial_stock": {"03 01 05": 0.5},
    }],
    "collectors": [{
        "id": "c", "waste_types": ["17 02 01", "99 99 99"], "collection_capacity": 1.0,
        "collection_frequency": 1.0, "transport_cost": 1.0, "efficiency": 1.0, "availability": True,
    }],
    "processors": [{
        "id": "p", "input_types": ["03 01 05"], "output_types": ["mdf", "plywood"],
        "processing_time": 1.0, "waste_storage_capacity": 10.0,
    }],
}


def test_ewc_strings_become_waste_types_in_file_order_and_unknown_codes_are_dropped():
    facilities = RegionalFacilities.from_dict(REGION_DATA)
    generator = facilities.generators[0]

    assert list(generator.waste_generation_rates.items()) == [
        (WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05, 2.0),
        (WasteType.CONSTRUCTION_WOOD_17_02_01, 3.0),
    ]
    assert generator.initial_stock == {WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: 0.5}
    assert facilities.collectors[0].waste_types == [WasteType.CONSTRUCTION_WOOD_17_02_01]
    assert facilities.processors[0].input_types == [WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05]
    assert facilities.processors[0].output_types == [OutputType.MDF]
