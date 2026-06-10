"""Tests for wiring the bullwhip namespace into the paired comparison (issue 07).

Drives the public ``build_paired_report`` seam against a tmp directory of
written ``run_*.json`` files, so the real loader -> flatten -> paired-t ->
Holm path is exercised end to end. The bullwhip KPIs live nested under
``kpis["bullwhip"]``; issue 07 lifts them to top-level ``bullwhip.{key}``
metrics that ride the existing all-combo-pairs machinery (no PUSH-vs-PULL
filter), generic over the namespace like issue 06.
"""

from analysis.paired_comparison import build_paired_report


def _find(rows, metric, combo_a, combo_b):
    """Return the report row for one metric/combo-pair, or None."""
    for row in rows:
        if row["metric"] == metric and row["combo_a"] == combo_a and row["combo_b"] == combo_b:
            return row
    return None


def test_nested_bullwhip_key_becomes_a_paired_comparison_metric(tmp_path, write_run):
    # Combo labels sort as pull__on_demand < push__on_demand, so the pair is
    # (combo_a=pull, combo_b=push) and the diff is pull - push.
    for seed, (push_v, pull_v) in enumerate([(1.0, 2.0), (1.0, 3.0), (1.0, 4.0)]):
        write_run(tmp_path, "push", "on_demand", seed, {"bullwhip": {"collector_stage": push_v}})
        write_run(tmp_path, "pull", "on_demand", seed, {"bullwhip": {"collector_stage": pull_v}})

    rows = build_paired_report(tmp_path)

    row = _find(rows, "bullwhip.collector_stage", "pull__on_demand", "push__on_demand")
    assert row is not None, "nested bullwhip key was not lifted to a comparable metric"
    # Per-seed pull - push = [1.0, 2.0, 3.0], mean 2.0 over 3 paired seeds.
    assert row["mean_diff"] == 2.0
    assert row["n_pairs"] == 3


def test_none_bullwhip_value_survives_flatten_and_drops_that_seed(tmp_path, write_run):
    # A lifted bullwhip key whose value is None on one seed must stay None (not
    # vanish) so the existing paired drop-on-None leaves a genuinely paired set.
    pulls = {0: 2.0, 1: None, 2: 4.0}
    for seed in (0, 1, 2):
        write_run(tmp_path, "push", "on_demand", seed, {"bullwhip": {"collector_stage": 1.0}})
        write_run(tmp_path, "pull", "on_demand", seed, {"bullwhip": {"collector_stage": pulls[seed]}})

    rows = build_paired_report(tmp_path)

    row = _find(rows, "bullwhip.collector_stage", "pull__on_demand", "push__on_demand")
    # Seed 1 dropped (pull is None): diffs over seeds 0,2 = [1.0, 3.0], mean 2.0.
    assert row["n_pairs"] == 2
    assert row["mean_diff"] == 2.0


def test_arbitrary_new_bullwhip_key_flows_through_without_wiring(tmp_path, write_run):
    # Generic over the namespace: a key never named in this module still
    # produces a comparison (acceptance criterion for issue 07).
    for seed in (0, 1):
        write_run(tmp_path, "push", "on_demand", seed, {"bullwhip": {"some_future_echelon": 1.0}})
        write_run(tmp_path, "pull", "on_demand", seed, {"bullwhip": {"some_future_echelon": 5.0}})

    rows = build_paired_report(tmp_path)

    row = _find(rows, "bullwhip.some_future_echelon", "pull__on_demand", "push__on_demand")
    assert row is not None
    assert row["mean_diff"] == 4.0


def _write_six_combo_grid(write_run, scenario_dir, bullwhip_value_for):
    """Write one run per (policy, strategy) x seed; bullwhip value via callback."""
    seeds = (0, 1, 2)
    for policy in ("push", "pull"):
        for strategy in ("on_demand", "reorder_50", "reorder_90"):
            for seed in seeds:
                write_run(
                    scenario_dir, policy, strategy, seed,
                    {
                        "service_level_full_pct": 90.0,
                        "bullwhip": {"collector_stage": bullwhip_value_for(policy, strategy, seed)},
                    },
                )


def test_bullwhip_metric_rides_all_fifteen_combo_pairs(tmp_path, write_run):
    # Six combos -> C(6,2) = 15 pairwise comparisons per metric, no PUSH-vs-PULL
    # filter; the curated flat metric is still reported alongside.
    _write_six_combo_grid(write_run, tmp_path, lambda policy, strategy, seed: seed + (1.0 if policy == "pull" else 0.0))

    rows = build_paired_report(tmp_path)

    bullwhip_rows = [r for r in rows if r["metric"] == "bullwhip.collector_stage"]
    curated_rows = [r for r in rows if r["metric"] == "service_level_full_pct"]
    assert len(bullwhip_rows) == 15
    assert len(curated_rows) == 15


def test_bullwhip_metrics_follow_curated_metrics_in_authored_order(tmp_path, write_run):
    for seed in (0, 1):
        kpis = {
            "service_level_full_pct": 90.0,
            "bullwhip": {"treatment_stage": 2.0, "collector_stage": 0.8},
        }
        write_run(tmp_path, "push", "on_demand", seed, kpis)
        write_run(tmp_path, "pull", "on_demand", seed, kpis)

    rows = build_paired_report(tmp_path)
    metric_order = list(dict.fromkeys(r["metric"] for r in rows))

    # Curated metric precedes any bullwhip metric...
    assert metric_order.index("service_level_full_pct") < metric_order.index("bullwhip.treatment_stage")
    # ...and bullwhip keys keep their authored insertion order (treatment before collector).
    assert metric_order.index("bullwhip.treatment_stage") < metric_order.index("bullwhip.collector_stage")


def test_all_none_bullwhip_metric_yields_no_comparison_row(tmp_path, write_run):
    # Unlike summary.csv (which keeps a count=0 discoverability row), a paired
    # report has nothing to compare when every value is None, so the metric is
    # dropped entirely -- same as any curated metric with an empty family.
    for seed in (0, 1):
        write_run(tmp_path, "push", "on_demand", seed, {"bullwhip": {"collector_stage": None}})
        write_run(tmp_path, "pull", "on_demand", seed, {"bullwhip": {"collector_stage": None}})

    rows = build_paired_report(tmp_path)

    assert all(r["metric"] != "bullwhip.collector_stage" for r in rows)


def test_explicit_metrics_list_suppresses_bullwhip_auto_append(tmp_path, write_run):
    # An explicit metric list is honored verbatim: no bullwhip key is appended
    # even though the runs carry one.
    for seed in (0, 1):
        write_run(tmp_path, "push", "on_demand", seed,
                   {"service_level_full_pct": 90.0, "bullwhip": {"collector_stage": 1.0}})
        write_run(tmp_path, "pull", "on_demand", seed,
                   {"service_level_full_pct": 80.0, "bullwhip": {"collector_stage": 5.0}})

    rows = build_paired_report(tmp_path, metrics=["service_level_full_pct"])

    assert any(r["metric"] == "service_level_full_pct" for r in rows)
    assert all(not r["metric"].startswith("bullwhip.") for r in rows)


def test_other_nested_kpi_dict_is_not_flattened_into_metrics(tmp_path, write_run):
    # Only the bullwhip namespace is lifted; the per-product service-level dict
    # must not explode into service_level_full_by_product_pct.MDF etc.
    for seed in (0, 1):
        kpis = {
            "service_level_full_by_product_pct": {"MDF": 90.0, "OSB": 80.0},
            "bullwhip": {"collector_stage": 1.0},
        }
        write_run(tmp_path, "push", "on_demand", seed, kpis)
        write_run(tmp_path, "pull", "on_demand", seed, kpis)

    rows = build_paired_report(tmp_path)

    assert all(not r["metric"].startswith("service_level_full_by_product_pct") for r in rows)
    # The bullwhip lift still happened on the same runs.
    assert any(r["metric"] == "bullwhip.collector_stage" for r in rows)


def test_constant_paired_difference_hits_zero_variance_branch(tmp_path, write_run):
    # A bullwhip key constant within each combo yields a constant paired diff,
    # exercising the existing zero-variance branch post-flatten: a nonzero
    # constant is deterministically significant (ADR 0007 identity flavor), a
    # zero constant is not -- both with zero sd.
    for seed in (0, 1, 2):
        write_run(tmp_path, "push", "on_demand", seed,
                   {"bullwhip": {"treatment_stage": 1.0, "collector_stage": 2.0}})
        write_run(tmp_path, "pull", "on_demand", seed,
                   {"bullwhip": {"treatment_stage": 3.0, "collector_stage": 2.0}})

    rows = build_paired_report(tmp_path)

    nonzero = _find(rows, "bullwhip.treatment_stage", "pull__on_demand", "push__on_demand")
    assert nonzero["sd_diff"] == 0.0
    assert nonzero["mean_diff"] == 2.0
    assert nonzero["significant_holm"] is True

    zero = _find(rows, "bullwhip.collector_stage", "pull__on_demand", "push__on_demand")
    assert zero["sd_diff"] == 0.0
    assert zero["mean_diff"] == 0.0
    assert zero["significant_holm"] is False


def test_residence_namespace_key_becomes_a_paired_comparison_metric(tmp_path, write_run):
    # The second generic namespace (C4) is flattened and discovered just like
    # bullwhip: a residence.* key rides the all-combo-pairs paired machinery.
    for seed, (push_v, pull_v) in enumerate([(1.0, 2.0), (1.0, 3.0), (1.0, 4.0)]):
        write_run(tmp_path, "push", "on_demand", seed,
                   {"residence": {"treatment_residence_days": push_v}})
        write_run(tmp_path, "pull", "on_demand", seed,
                   {"residence": {"treatment_residence_days": pull_v}})

    rows = build_paired_report(tmp_path)

    row = _find(rows, "residence.treatment_residence_days",
                "pull__on_demand", "push__on_demand")
    assert row is not None, "residence key was not lifted to a comparable metric"
    # Per-seed pull - push = [1.0, 2.0, 3.0], mean 2.0 over 3 paired seeds.
    assert row["mean_diff"] == 2.0
    assert row["n_pairs"] == 3
