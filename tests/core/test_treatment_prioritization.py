"""Tests for ABC transformation prioritization (ADR 0002, Phase F / Q8).

The scorer ranks (input, output) transformations so production steers toward
the product whose finished-goods buffer is most depleted. These tests drive
``_get_prioritized_transformations`` directly as an unbound method over a
lightweight stand-in ``self`` -- the scorer reads only inventory state, no
SimPy clock or full operator construction required.
"""

from types import SimpleNamespace

from core.treatment import TreatmentOperator
from models.enums import OutputType, WasteType


def make_self(finished_goods_storage, capacity, abc_priority_map=None, waste=100.0):
    """A minimal stand-in exposing exactly what the scorer reads.

    One transformation per producible output, all sharing the same input waste
    type, efficiency, and on-hand input volume so the finished-goods shortfall
    term is the only differentiator unless ``abc_priority_map`` is supplied.
    """
    input_type = WasteType.OTHER_WOOD_WASTE_03_01_99
    transformations = {
        (input_type, output_type): SimpleNamespace(name=output_type.value)
        for output_type in (OutputType.MDF, OutputType.PARTICLE_BOARD, OutputType.OSB)
    }
    finished_goods = SimpleNamespace(
        capacity={OutputType(p): c for p, c in capacity.items()},
        current_storage={OutputType(p): v for p, v in finished_goods_storage.items()},
    )
    return SimpleNamespace(
        transformations=transformations,
        abc_priority_map=abc_priority_map or {"mdf": 0.5, "particle_board": 0.5, "osb": 0.5},
        finished_goods=finished_goods,
        waste_storage={input_type: waste},
        _get_transformation_efficiency=lambda transformation: 0.9,
    )


def output_order(prioritized):
    """Extract the output-type ordering from the scorer's return value."""
    return [output_type for (_input, output_type), _transform in prioritized]


def test_most_depleted_output_ranks_first():
    """With ABC priority, efficiency, and input held equal, the output whose
    finished-goods buffer is most depleted relative to capacity scores highest."""
    fake = make_self(
        finished_goods_storage={"mdf": 90.0, "particle_board": 50.0, "osb": 10.0},
        capacity={"mdf": 100.0, "particle_board": 100.0, "osb": 100.0},
    )

    ordering = output_order(TreatmentOperator._get_prioritized_transformations(fake))

    assert ordering == [OutputType.OSB, OutputType.PARTICLE_BOARD, OutputType.MDF]


def test_full_buffer_scores_below_depleted_buffer():
    """A saturated buffer contributes zero shortfall and ranks last."""
    fake = make_self(
        finished_goods_storage={"mdf": 100.0, "particle_board": 60.0, "osb": 0.0},
        capacity={"mdf": 100.0, "particle_board": 100.0, "osb": 100.0},
    )

    ordering = output_order(TreatmentOperator._get_prioritized_transformations(fake))

    assert ordering[0] == OutputType.OSB
    assert ordering[-1] == OutputType.MDF


def test_demand_ceiling_api_stays_retired():
    """The legacy demand-ceiling control surface must stay deleted.

    Ceiling retirement removed these accessors; the scorer now steers on
    finished-goods shortfall only. Re-introducing any of them would resurrect
    the retired ceiling, so guard against it. The scorer must still run with no
    ceiling present.
    """
    from models.state import SimulationState

    for attr in (
        "get_unmet_demands",
        "check_all_demands_met",
        "track_product_production",
    ):
        assert not hasattr(SimulationState, attr), f"ceiling symbol resurrected: {attr}"

    fake = make_self(
        finished_goods_storage={"mdf": 10.0, "particle_board": 50.0, "osb": 90.0},
        capacity={"mdf": 100.0, "particle_board": 100.0, "osb": 100.0},
    )

    # Must not raise -- the scorer reads only finished-goods inventory state.
    TreatmentOperator._get_prioritized_transformations(fake)


def test_zero_capacity_output_contributes_no_shortfall():
    """An output with zero finished-goods capacity yields a zero shortfall term
    rather than dividing by zero."""
    fake = make_self(
        finished_goods_storage={"mdf": 0.0, "particle_board": 0.0, "osb": 0.0},
        capacity={"mdf": 0.0, "particle_board": 100.0, "osb": 100.0},
    )

    # The two capacitated, fully-depleted outputs outrank the zero-capacity one.
    ordering = output_order(TreatmentOperator._get_prioritized_transformations(fake))

    assert ordering[-1] == OutputType.MDF
