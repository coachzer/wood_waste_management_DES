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
