"""Tests for the stochastic-dominance reduction (C6).

Exercises the pure dominance core (``first_order_dominance`` /
``second_order_dominance`` / ``dominance_relation``) on hand-built distributions
with a known relation, then the dataset path (``build_dominance_report`` /
``write_dominance_report``) against tmp ``run_*.json`` files. No simulation run --
mirrors the synthetic-fixture style of ``test_pareto.py`` / ``test_bullwhip.py``.

The dominance math is on the *raw* values as a "stochastically larger" relation
(F_A <= F_B, i.e. A's distribution sits to the right of B's). The per-KPI sense
is interpretation layered on top -- whether "larger" means "better" -- so these
core tests are sense-free; sense annotation is checked at the report layer.
"""

import json

from monitoring.stochastic_dominance import (
    KPI_SENSES,
    build_dominance_report,
    dominance_relation,
    first_order_dominance,
    second_order_dominance,
    write_dominance_report,
)


def _write_run(combo_dir, policy, strategy, seed, kpis):
    """Write one run_<seed>.json with the fields load_combo_kpis reads."""
    combo_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "inventory_policy": policy,
        "stock_strategy": strategy,
        "seed": seed,
        "kpis": kpis,
    }
    (combo_dir / f"run_{seed}.json").write_text(json.dumps(run), encoding="utf-8")


# --- first-order dominance -------------------------------------------------

def test_fsd_when_one_distribution_is_shifted_up():
    # A is B shifted up by 1: F_A lies entirely at/below F_B -> A FSD B.
    higher = [2.0, 3.0, 4.0]
    lower = [1.0, 2.0, 3.0]
    assert first_order_dominance(higher, lower) == "a"
    assert first_order_dominance(lower, higher) == "b"


def test_fsd_none_when_cdfs_cross():
    # Equal means, crossing CDFs -> no first-order relation either way.
    a = [1.0, 4.0]
    b = [2.0, 3.0]
    assert first_order_dominance(a, b) is None


def test_fsd_none_for_identical_distributions():
    # No strict improvement anywhere -> neither dominates.
    same = [1.0, 2.0, 3.0]
    assert first_order_dominance(same, list(same)) is None


# --- second-order dominance ------------------------------------------------

def test_ssd_for_mean_preserving_contraction():
    # Same mean (2.0); A is tighter than the spread B=[1,3]. The risk-averse
    # (integrated-CDF) condition holds: A SSD B, though neither FSD-dominates.
    tight = [2.0, 2.0]
    spread = [1.0, 3.0]
    assert first_order_dominance(tight, spread) is None
    assert second_order_dominance(tight, spread) == "a"
    assert second_order_dominance(spread, tight) == "b"


def test_ssd_none_when_higher_mean_but_too_spread():
    # A has the higher mean (3 vs 2) but so much more spread that the integrated
    # CDF difference changes sign -> neither second-order dominates.
    a = [1.0, 5.0]
    b = [2.0, 2.0]
    assert first_order_dominance(a, b) is None
    assert second_order_dominance(a, b) is None


def test_ssd_none_for_identical_distributions():
    same = [1.0, 2.0, 3.0]
    assert second_order_dominance(same, list(same)) is None


# --- combined relation (strongest order) -----------------------------------

def test_relation_reports_fsd_as_strongest_order():
    # When FSD holds it also implies SSD; the relation must report the stronger.
    assert dominance_relation([2.0, 3.0, 4.0], [1.0, 2.0, 3.0]) == ("FSD", "a")


def test_relation_reports_ssd_when_only_second_order_holds():
    assert dominance_relation([2.0, 2.0], [1.0, 3.0]) == ("SSD", "a")


def test_relation_reports_none_when_incomparable():
    assert dominance_relation([1.0, 5.0], [2.0, 2.0]) == ("none", None)


# --- dataset reader / report ----------------------------------------------

def test_build_dominance_report_maps_winner_and_sense(tmp_path):
    # push__on_demand FSD-dominates pull__on_demand on a "max" KPI (service):
    # push has the larger, better distribution.
    for seed, (push_v, pull_v) in enumerate(
        [(90.0, 50.0), (92.0, 55.0), (94.0, 60.0)], start=1
    ):
        _write_run(
            tmp_path / "push__on_demand", "push", "on_demand", seed,
            {"service_level_full_pct": push_v},
        )
        _write_run(
            tmp_path / "pull__on_demand", "pull", "on_demand", seed,
            {"service_level_full_pct": pull_v},
        )
    rows = build_dominance_report(tmp_path, metrics=["service_level_full_pct"])
    assert len(rows) == 1
    row = rows[0]
    assert row["metric"] == "service_level_full_pct"
    assert {row["combo_a"], row["combo_b"]} == {"push__on_demand", "pull__on_demand"}
    assert row["dominance_order"] == "FSD"
    assert row["dominant_combo"] == "push__on_demand"
    assert row["sense"] == "max"
    assert row["n_a"] == 3 and row["n_b"] == 3


def test_build_dominance_report_records_no_dominance(tmp_path):
    # Crossing CDFs with equal means -> no dominance; the pair is still reported.
    for seed, (a_v, b_v) in enumerate([(1.0, 2.0), (5.0, 2.0)], start=1):
        _write_run(tmp_path / "push__on_demand", "push", "on_demand", seed,
                   {"landfill_volume_m3": a_v})
        _write_run(tmp_path / "pull__on_demand", "pull", "on_demand", seed,
                   {"landfill_volume_m3": b_v})
    rows = build_dominance_report(tmp_path, metrics=["landfill_volume_m3"])
    assert len(rows) == 1
    assert rows[0]["dominance_order"] == "none"
    assert rows[0]["dominant_combo"] == ""
    assert rows[0]["sense"] == "min"


def test_build_dominance_report_drops_combo_with_too_few_samples(tmp_path):
    # A single replication is not a distribution -> the pair is skipped.
    _write_run(tmp_path / "push__on_demand", "push", "on_demand", 1,
               {"service_level_full_pct": 90.0})
    _write_run(tmp_path / "pull__on_demand", "pull", "on_demand", 1,
               {"service_level_full_pct": 50.0})
    _write_run(tmp_path / "pull__on_demand", "pull", "on_demand", 2,
               {"service_level_full_pct": 55.0})
    assert build_dominance_report(tmp_path, metrics=["service_level_full_pct"]) == []


def test_write_dominance_report_round_trips(tmp_path):
    for seed, (push_v, pull_v) in enumerate([(90.0, 50.0), (92.0, 55.0)], start=1):
        _write_run(tmp_path / "push__on_demand", "push", "on_demand", seed,
                   {"total_emissions_kgco2e": push_v})
        _write_run(tmp_path / "pull__on_demand", "pull", "on_demand", seed,
                   {"total_emissions_kgco2e": pull_v})
    report = write_dominance_report(tmp_path, metrics=["total_emissions_kgco2e"])
    assert report == tmp_path / "stochastic_dominance.csv"
    header, *data_lines = report.read_text(encoding="utf-8").splitlines()
    assert header == (
        "metric,combo_a,combo_b,n_a,n_b,dominance_order,dominant_combo,sense"
    )
    assert len(data_lines) == 1
    fields = data_lines[0].split(",")
    assert fields[0] == "total_emissions_kgco2e"
    assert fields[5] == "FSD"  # dominance_order
    # emissions is a "min" KPI: the stochastically-larger combo is the worse one.
    assert fields[7] == "min"  # sense


def test_write_dominance_report_empty_dir_returns_none(tmp_path):
    assert build_dominance_report(tmp_path) == []
    assert write_dominance_report(tmp_path) is None


def test_kpi_senses_cover_the_paired_default_metrics():
    # Every curated headline metric must have a documented sense so the report
    # can interpret "larger" as better or worse.
    from monitoring.stochastic_dominance import DEFAULT_METRICS

    for metric in DEFAULT_METRICS:
        assert KPI_SENSES[metric] in ("max", "min")
