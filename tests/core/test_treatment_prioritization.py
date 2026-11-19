"""Tests for ABC transformation prioritization (ADR 0002, Phase F / Q8).

The scorer ranks (input, output) transformations so production steers toward
the product whose finished-goods buffer is most depleted. The ranking tests
read ``_get_prioritized_transformations`` on a real operator, because the full
order is not visible in one tick of output; the last test checks the visible
effect, that the input goes to the most depleted product.
"""

import simpy

from models.enums import OutputType, WasteType
from tests.core.factories import make_treatment

INPUT = WasteType.OTHER_WOOD_WASTE_03_01_99


def make_operator(ledger_waste_monitor, finished_goods_storage, capacity, waste=100.0, env=None):
    """A real operator with one route per product from one input type.

    Routes share input, catalogue efficiency, on-hand volume and an equal ABC
    weight, so the finished-goods shortfall term is the only differentiator.
    """
    operator = make_treatment(
        env or simpy.Environment(), ledger_waste_monitor,
        initial_waste_storage={INPUT: waste},
        finished_goods_capacity={OutputType(product): volume for product, volume in capacity.items()},
        order_share_by_waste_type={INPUT: 1.0}, order_up_to_level_m3=waste,
        abc_priority_map={"mdf": 0.5, "particle_board": 0.5, "osb": 0.5},
    )
    for product, volume in finished_goods_storage.items():
        operator.finished_goods.current_storage[OutputType(product)] = volume
    return operator


def output_order(prioritized):
    """Extract the output-type ordering from the scorer's return value."""
    return [output_type for (_input, output_type), _transform in prioritized]


def test_most_depleted_output_ranks_first(ledger_waste_monitor):
    """With ABC priority, efficiency, and input held equal, the output whose
    finished-goods buffer is most depleted relative to capacity scores highest."""
    operator = make_operator(
        ledger_waste_monitor,
        finished_goods_storage={"mdf": 90.0, "particle_board": 50.0, "osb": 10.0},
        capacity={"mdf": 100.0, "particle_board": 100.0, "osb": 100.0},
    )

    ordering = output_order(operator._get_prioritized_transformations())

    assert ordering == [OutputType.OSB, OutputType.PARTICLE_BOARD, OutputType.MDF]


def test_zero_capacity_output_contributes_no_shortfall(ledger_waste_monitor):
    """An output with zero finished-goods capacity yields a zero shortfall term
    rather than dividing by zero."""
    operator = make_operator(
        ledger_waste_monitor,
        finished_goods_storage={"mdf": 0.0, "particle_board": 0.0, "osb": 0.0},
        capacity={"mdf": 0.0, "particle_board": 100.0, "osb": 100.0},
    )

    # The two capacitated, fully-depleted outputs outrank the zero-capacity one.
    ordering = output_order(operator._get_prioritized_transformations())

    assert ordering[-1] == OutputType.MDF


def test_one_tick_of_production_goes_to_the_most_depleted_product(ledger_waste_monitor):
    """10 m3 of input is used up by the first-ranked route, so only OSB grows.

    Mutation check (red): sort the scores ascending -> MDF (fullest) grows instead.
    """
    env = simpy.Environment()
    operator = make_operator(
        ledger_waste_monitor,
        finished_goods_storage={"mdf": 90.0, "particle_board": 50.0, "osb": 10.0},
        capacity={"mdf": 100.0, "particle_board": 100.0, "osb": 100.0},
        waste=10.0,
        env=env,
    )
    before = dict(operator.finished_goods.current_storage)

    env.run(until=0.5)

    grown = {product for product, volume in operator.finished_goods.current_storage.items() if volume > before[product]}
    assert grown == {OutputType.OSB}
    assert operator.waste_storage[INPUT] == 0.0
