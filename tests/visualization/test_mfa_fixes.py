"""Focused behavior tests for mfa_visualization.py fixes."""

from types import SimpleNamespace

from config.constants import MFA_MIN_FLOW_VOLUME_M3
from visualization.mfa_visualization import (
    STOCK_NODE_NAME,
    _stock_at_end_by_entity,
    create_material_flow_analysis,
    create_sankey,
    get_volumes,
)


def test_dynamic_product_discovery_and_flow_threshold():
    op = SimpleNamespace(
        name="treat_1",
        current_storage=25.0,
        product_volumes={
            "mdf": 100.0,
            "biochar": MFA_MIN_FLOW_VOLUME_M3 + 1.0,
            "wood_pellets": MFA_MIN_FLOW_VOLUME_M3 / 2.0,
        },
    )
    state = SimpleNamespace(
        transport_flows=[],
        treatment_operators=[op],
        generators=[],
        collectors=[],
    )
    gen_vol, sink_vol, col_vol, treat_vol, prod_vol = get_volumes(
        {}, {}, {"treat_1": {"processed": {"total": [150.0]}}}, state
    )
    assert "MDF" in prod_vol
    assert "Biochar" in prod_vol
    assert "Wood Pellets" in prod_vol

    labels, _, sources, targets, values, _, _, _ = create_sankey(
        gen_vol, sink_vol, col_vol, {"treat_1": 150.0}, prod_vol, state
    )
    label_names = [lbl.split("\n", 1)[0] for lbl in labels]
    assert "Biochar" in label_names
    assert STOCK_NODE_NAME in label_names
    # Treatment->product link for Biochar uses MFA_MIN_FLOW_VOLUME_M3
    biochar_idx = label_names.index("Biochar")
    assert biochar_idx in targets


def test_stock_at_end_includes_treatment_waste_storage():
    state = SimpleNamespace(
        generators=[SimpleNamespace(name="gen_1", current_storage=10.0)],
        collectors=[
            SimpleNamespace(
                name="col_1",
                collection_center=SimpleNamespace(current_storage={"17 02 01": 20.0}),
            )
        ],
        treatment_operators=[SimpleNamespace(name="treat_1", current_storage=30.0)],
    )
    stock = _stock_at_end_by_entity(state)
    assert stock == {"gen_1": 10.0, "col_1": 20.0, "treat_1": 30.0}


def test_inter_region_transport_preserves_collector_with_zero_direct_collection():
    state = SimpleNamespace(
        transport_flows=[
            {
                "source_name": "col_a",
                "target_name": "col_b",
                "volume": 200.0,
                "transport_method": "inter_region_transport",
            },
            {
                "source_name": "col_b",
                "target_name": "treat_1",
                "volume": 200.0,
                "transport_method": "treatment_intake",
            },
        ],
        treatment_operators=[],
        generators=[],
        collectors=[],
    )
    labels, _, sources, targets, values, _, _, _ = create_sankey(
        {}, {}, {"col_a": 200.0, "col_b": 0.0}, {"treat_1": 200.0}, {}, state
    )
    label_names = [lbl.split("\n", 1)[0] for lbl in labels]
    assert "col_b" in label_names
    assert len(sources) == 2
    assert values == [200.0, 200.0]


def test_create_material_flow_analysis_omits_none_scenario_and_uses_path_suffix(tmp_path):
    state = SimpleNamespace(
        transport_flows=[],
        treatment_operators=[],
        generators=[],
        collectors=[],
    )
    out_dir = tmp_path / "run.html_dir"
    save_path = str(out_dir / "mfa.html")
    written = create_material_flow_analysis(
        {},
        {},
        {},
        state,
        scenario_name=None,
        inventory_policy="push",
        stock_strategy="on_demand",
        save_path=save_path,
    )
    assert written == save_path
    html = (out_dir / "mfa.html").read_text(encoding="utf-8")
    assert "Scenario: None" not in html
    assert "Inventory Policy: push" in html
