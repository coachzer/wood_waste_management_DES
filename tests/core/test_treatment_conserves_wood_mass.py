"""Treatment converts waste mass, not loose waste volume, into panel volume (ADR 0043)."""
import pytest
import simpy

from config.constants import PANEL_DENSITIES, WASTE_DENSITIES
from models.enums import OutputType, WasteType
from models.transformations import TRANSFORMATION_CATALOGUE, WASTE_TO_OUTPUT_TYPES, volumetric_yield
from tests.core.test_operating_clock import CONSTRUCTION, _treatment


def test_processed_waste_tonnes_times_efficiency_equal_panel_tonnes():
    operator = _treatment(simpy.Environment())
    transformation = operator.transformations[(CONSTRUCTION, OutputType.PARTICLE_BOARD)]

    output_m3 = operator._process_waste_transformation(CONSTRUCTION, OutputType.PARTICLE_BOARD, transformation)

    input_tonnes = operator.processed_volumes[CONSTRUCTION] * WASTE_DENSITIES[CONSTRUCTION] / 1000
    output_tonnes = output_m3 * PANEL_DENSITIES[OutputType.PARTICLE_BOARD] / 1000
    assert input_tonnes > 0
    assert output_tonnes == pytest.approx(input_tonnes * transformation.conversion_efficiency)
    assert operator.expected_output_volume_from_intake_m3 == pytest.approx(output_m3)


@pytest.mark.parametrize(
    "input_type,output_type",
    [(input_type, output_type) for input_type, outputs in WASTE_TO_OUTPUT_TYPES.items() for output_type in outputs],
)
def test_no_catalogue_route_makes_more_panel_mass_than_waste_mass(input_type, output_type):
    efficiency, _ = TRANSFORMATION_CATALOGUE[input_type]
    panel_m3_per_waste_m3 = volumetric_yield(efficiency, input_type, output_type)
    assert panel_m3_per_waste_m3 * PANEL_DENSITIES[output_type] <= WASTE_DENSITIES[input_type]
    assert panel_m3_per_waste_m3 * PANEL_DENSITIES[output_type] == pytest.approx(efficiency * WASTE_DENSITIES[input_type])
