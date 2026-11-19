"""Regression test for the storage-heatmap grouping assertion (VIZ-REVIEW T2).

Failure mode guarded: ``create_storage_heatmaps`` raised
``ValueError("Grouping failed")`` whenever ``len(grouped_results) >= len(results)``
-- which fires for any run where no two combos share
``(base_scenario, inventory_policy)``, including a single-combo run
(1 group >= 1 result). The assertion encoded a false invariant that only held
because the standard grid bundles three stock strategies per policy.

Non-vacuity: a single-combo run produces one group from one result, so the
pre-fix assertion makes this test red.
"""

from visualization.storage_visualization import create_storage_heatmaps


def _single_combo_result():
    samples = {"timestamps": [0.0, 1.0], "storage_utilization": [10.0, 20.0]}
    return {
        "base_scenario": "Baseline",
        "scenario_name": "Baseline_push_on_demand",
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
        "monitor_data": {
            "generation_history": {"gen_1": dict(samples)},
            "collection_history": {"col_1": dict(samples)},
            "processing_history": {
                "proc_1": {
                    "timestamps": [0.0, 1.0],
                    "storage": {
                        "waste_utilization": [10.0, 20.0],
                        "finished_goods_utilization": [5.0, 15.0],
                    },
                }
            },
        },
    }


def test_single_combo_run_does_not_raise(tmp_path):
    # One result -> one group; the old assertion (1 >= 1) crashed here.
    create_storage_heatmaps([_single_combo_result()], str(tmp_path))
    heatmap_dir = tmp_path / "storage_heatmaps" / "entity_storage" / "generation"
    assert any(heatmap_dir.glob("*.html"))


def test_empty_results_still_rejected(tmp_path):
    # The legitimate empty-input guard must survive removal of the false one.
    try:
        create_storage_heatmaps([], str(tmp_path))
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty results")


def test_extract_heatmap_matrix_numpy_array_and_single_timestamp():
    import numpy as np
    from visualization.visualization_utils import extract_heatmap_matrix

    history = {
        "gen_1": {
            "timestamps": [5.0],
            "storage_utilization": np.array([42.0]),
        }
    }
    data = extract_heatmap_matrix(history, lambda d: d.get("storage_utilization"))
    assert list(data["x_values"]) == [5.0]
    assert data["y_values"] == ["gen_1"]
    assert list(data["z_values"][0]) == [42.0]


def test_storage_heatmaps_colorbar_on_first_nonempty_and_many_strategies(tmp_path):
    # First strategy has empty generation_history; second is non-empty; 10 strategies test vertical_spacing clamping.
    results = []
    for idx in range(10):
        gen_hist = {} if idx == 0 else {"gen_1": {"timestamps": [0.0, 1.0], "storage_utilization": [10.0, 20.0]}}
        results.append({
            "base_scenario": "Baseline",
            "scenario_name": f"Baseline_push_strat_{idx}",
            "inventory_policy": "push",
            "stock_strategy": f"strat_{idx}",
            "monitor_data": {
                "generation_history": gen_hist,
                "collection_history": {"col_1": {"timestamps": [0.0, 1.0], "storage_utilization": [10.0, 20.0]}},
                "processing_history": {
                    "proc_1": {
                        "timestamps": [0.0, 1.0],
                        "storage": {
                            "waste_utilization": [10.0, 20.0],
                            "finished_goods_utilization": [5.0, 15.0],
                        },
                    }
                },
            },
        })
    create_storage_heatmaps(results, str(tmp_path))
    gen_html = (tmp_path / "storage_heatmaps" / "entity_storage" / "generation" / "generation_storage_heatmap_Baseline_push.html").read_text(encoding="utf-8")
    assert '"showscale":true' in gen_html
