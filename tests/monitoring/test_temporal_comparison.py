"""Focused behavior tests for temporal_comparison.py fixes."""

import pytest

from visualization.temporal_comparison import (
    _add_cost_efficiency_bar_chart,
    _calculate_collection_metrics,
    _create_efficiency_subplot_figure,
    _create_entity_status_view,
    _create_metric_comparison,
    _extract_efficiency_metrics,
    extract_total_costs_from_monitor_data,
)


def test_extract_total_costs_includes_holding_costs():
    monitor_data = {
        "generation_history": {"gen_1": {"timestamps": [1.0], "holding_costs": [10.0]}},
        "collection_history": {
            "col_1": {"timestamps": [1.0], "total_costs": [20.0], "holding_costs": [5.0]}
        },
        "processing_history": {
            "proc_1": {
                "timestamps": [1.0],
                "operational": {"total_costs": [30.0], "holding_costs": [15.0]},
            }
        },
        "event_history": {},
    }
    costs = extract_total_costs_from_monitor_data(monitor_data)
    assert costs == {1.0: 80.0}


def test_calculate_collection_metrics_excludes_outlet_per_adr_0036():
    monitor_data = {
        "generation_history": {
            "gen_1": {
                "total_potential_generated": {"17 02 01": [100.0], "20 03 07": [100.0]},
                "total_outlet": {"17 02 01": [0.0], "20 03 07": [100.0]},
            }
        },
        "collection_history": {"col_1": {"collected_volumes": {"17 02 01": [75.0]}}},
    }
    metrics = _calculate_collection_metrics(monitor_data)
    assert metrics["collection_efficiency"] == pytest.approx(75.0)


def test_metric_comparison_scales_efficiency_to_percent(tmp_path):
    from visualization.visualization_utils import calculate_average_efficiency

    results = [
        {
            "scenario_name": "Baseline_push_on_demand",
            "monitor_data": {
                "collection_history": {
                    "col_1": {"timestamps": [0.0, 1.0], "efficiency": [0.5, 0.8]}
                }
            },
        }
    ]
    spec = {
        "subdir": "collection",
        "history_key": "collection_history",
        "aggregate": calculate_average_efficiency,
        "value_key": "efficiency",
        "scale": 100.0,
        "title": "Collection Efficiency Over Time",
        "y_title": "Average Efficiency (%)",
        "filename": "collection_efficiency_comparison",
        "message": "saved",
    }
    _create_metric_comparison(results, str(tmp_path), spec)
    html = (tmp_path / "collection_efficiency_comparison.html").read_text(encoding="utf-8")
    assert "[50.0,80.0]" in html or "[50,80]" in html


def test_cost_efficiency_bar_chart_handles_stalled_inf_and_multi_scenario_labels():
    results = [
        {
            "base_scenario": "Baseline",
            "inventory_policy": "push",
            "stock_strategy": "on_demand",
            "monitor_data": {
                "generation_history": {},
                "collection_history": {"col_1": {"timestamps": [1.0], "total_costs": [100.0]}},
                "processing_history": {},
                "environmental_history": {},
            },
        },
        {
            "base_scenario": "Stress",
            "inventory_policy": "push",
            "stock_strategy": "on_demand",
            "monitor_data": {
                "generation_history": {},
                "collection_history": {"col_1": {"timestamps": [1.0], "total_costs": [200.0]}},
                "processing_history": {"proc_1": {"processed": {"total": [10.0]}}},
                "environmental_history": {},
            },
        },
    ]
    scenario_data = _extract_efficiency_metrics(results)
    fig = _create_efficiency_subplot_figure()
    _add_cost_efficiency_bar_chart(fig, scenario_data)
    bar = fig.data[0]
    assert list(bar.x) == ["Stress | push | on_demand", "Baseline | push | on_demand"]
    assert list(bar.y) == [20.0, None]
    assert list(bar.text) == ["", "N/A"]


def test_entity_status_view_labels_entities_dedups_legend_and_clamps_spacing(tmp_path):
    results = []
    for idx in range(10):
        results.append({
            "base_scenario": "Baseline",
            "inventory_policy": "push",
            "stock_strategy": f"strat_{idx}",
            "monitor_data": {
                "generation_history": {
                    "gen_alpha": {"timestamps": [0.0, 1.0, 2.0], "status": ["OPERATIONAL", "FAILED", "OPERATIONAL"]},
                    "gen_beta": {"timestamps": [0.0], "status": ["RECOVERING"]},
                },
                "collection_history": {},
                "processing_history": {},
            },
        })
    _create_entity_status_view(results, str(tmp_path))
    html = (
        tmp_path
        / "entity_status"
        / "generator_status_timeline_Baseline_push.html"
    ).read_text(encoding="utf-8")
    assert "gen_alpha" in html
    assert "gen_beta" in html
    assert '"mode":"lines+markers"' in html
