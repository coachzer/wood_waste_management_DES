"""Regression test for the summary-dashboard "Event Cost" panel (VIZ-REVIEW T1).

Failure mode guarded: ``create_summary_dashboard`` read the non-existent key
``event_history['total_cost']['values']``, so the Event Cost panel was
permanently 0 regardless of the recorded overflow cost. The recorded schema is
``event_history['system_events']['total_costs']`` -- a list of per-event cost
increments -- summed exactly as ``create_cost_impact_comparison`` does.

Non-vacuity: with all other metrics zero (empty histories), the distinctive
summed value appears as a bar label in the dashboard HTML only when the correct
key is read; the pre-fix dead-key path (always 0) makes the assertion red.
"""

from visualization.summary_visualization import create_summary_dashboard


def _result_with_overflow_costs(total_costs):
    """A minimal result whose only non-empty event stream is overflow cost."""
    return {
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
        "monitor_data": {
            "generation_history": {},
            "collection_history": {},
            "processing_history": {},
            "event_history": {"system_events": {"total_costs": total_costs}},
        },
    }


def _dashboard_html(output_dir):
    return (output_dir / "summary_dashboard.html").read_text(encoding="utf-8")


def test_event_cost_sums_system_event_increments(tmp_path):
    # Increments sum to 612345.0 -- a value no zero-valued metric can produce,
    # and the dashboard renders each bar's value via an f"{val:.1f}" label.
    create_summary_dashboard(
        [_result_with_overflow_costs([12000.0, 345.0, 600000.0])], str(tmp_path)
    )
    assert "612345.0" in _dashboard_html(tmp_path)


def test_empty_overflow_stream_does_not_crash(tmp_path):
    # An empty stream must read 0 without raising -- guards the fix's gap handling.
    create_summary_dashboard([_result_with_overflow_costs([])], str(tmp_path))
    assert (tmp_path / "summary_dashboard.html").exists()


def test_create_scenario_label_includes_base_scenario_when_present():
    from visualization.visualization_utils import create_scenario_label

    assert create_scenario_label({
        "base_scenario": "Baseline",
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
    }) == "Baseline | push | on_demand"
    assert create_scenario_label({
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
    }) == "push | on_demand"


def test_cost_impact_comparison_includes_holding_costs_and_clean_legend(tmp_path):
    from visualization.summary_visualization import create_cost_impact_comparison

    result = {
        "base_scenario": "Baseline",
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
        "monitor_data": {
            "generation_history": {"gen_1": {"holding_costs": [100.0]}},
            "collection_history": {"col_1": {"energy_costs": [50.0], "holding_costs": [25.0]}},
            "processing_history": {"proc_1": {"operational": {"holding_costs": [30.0]}}},
            "event_history": {},
        },
    }
    create_cost_impact_comparison([result], str(tmp_path / "nested"))
    html = (tmp_path / "nested" / "cost_breakdown_comparison.html").read_text(encoding="utf-8")
    assert "Holding Costs" in html
    assert "Energy Costs" in html
    assert "155" in html  # 100 + 25 + 30 total holding cost


def test_summary_dashboard_excludes_outlet_from_collection_efficiency(tmp_path):
    result = {
        "base_scenario": "Baseline",
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
        "monitor_data": {
            "generation_history": {
                "gen_1": {
                    "total_potential_generated": {"17 02 01": [100.0], "20 03 07": [100.0]},
                    "total_outlet": {"17 02 01": [0.0], "20 03 07": [100.0]},
                }
            },
            "collection_history": {"col_1": {"collected_volumes": {"17 02 01": [80.0]}}},
            "processing_history": {},
            "event_history": {},
        },
    }
    create_summary_dashboard([result], str(tmp_path))
    # 80 / (200 - 100) * 100 = 80.0%, NOT 80 / 200 * 100 = 40.0%
    metrics_html = (tmp_path / "metrics_summary.html").read_text(encoding="utf-8")
    assert "80.0" in metrics_html


def test_empty_results_handled_cleanly_in_summary_functions(tmp_path):
    from visualization.summary_visualization import create_cost_impact_comparison

    out_dir = tmp_path / "empty_out"
    create_cost_impact_comparison([], str(out_dir))
    create_summary_dashboard([], str(out_dir))
    assert out_dir.exists()
