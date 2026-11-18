"""The MFA Sankey shows potential generation and routes the overflow to an Uncollected sink (ADR 0024)."""
from types import SimpleNamespace

from visualization.mfa_visualization import create_sankey, get_volumes


def _generation_history():
    return {
        "gen_a": {
            "total_generated": {"17 02 01": [0.0, 600.0]},
            "total_potential_generated": {"17 02 01": [0.0, 1000.0]},
            "total_uncollected": {"17 02 01": [0.0, 400.0]},
        }
    }


def test_generator_node_reports_potential_generation_and_overflow_reaches_the_sink():
    """Mutation check (red): read total_generated, or drop the Uncollected links."""
    state = SimpleNamespace(transport_flows=[], treatment_operators=[])
    generators, uncollected, collectors, treatments, products = get_volumes(_generation_history(), {}, {}, state)

    labels, _, sources, targets, values, _, x, y = create_sankey(
        generators, uncollected, collectors, treatments, products, state
    )

    assert labels == ["gen_a\n1.0k m³", "Uncollected\n400.0 m³"]
    assert list(zip(sources, targets, values)) == [(0, 1, 400.0)]
    assert len(x) == len(y) == len(labels)
