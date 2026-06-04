"""Tests for the Pareto-frontier reduction (C5).

Exercises the pure domination core (``dominates`` / ``pareto_frontier``) on
hand-built fixtures with known frontiers, then the dataset path
(``read_objective_point`` / ``build_pareto_report`` / ``write_pareto_report``)
against tmp ``summary.csv`` files in both scenario and ``--root`` layouts. No
simulation run -- mirrors the synthetic-fixture style of ``test_bullwhip.py``.
"""

from monitoring.pareto import (
    OBJECTIVES,
    build_pareto_report,
    dominates,
    pareto_frontier,
    read_objective_point,
    write_pareto_report,
)

# Two all-minimize objectives keep the hand-computed frontier easy to verify.
MIN_MIN = [("a", "min"), ("b", "min")]


def _write_summary(combo_dir, means):
    """Write a minimal summary.csv (the real header + a row per metric)."""
    combo_dir.mkdir(parents=True, exist_ok=True)
    lines = ["metric,mean,stdev,ci95_low,ci95_high,count"]
    for metric, mean in means.items():
        lines.append(f"{metric},{mean},0,0,0,10")
    (combo_dir / "summary.csv").write_text("\n".join(lines), encoding="utf-8")


# --- domination core -------------------------------------------------------

def test_dominates_strict_single_objective():
    better = {"a": 1.0, "b": 1.0}
    worse = {"a": 2.0, "b": 1.0}
    assert dominates(better, worse, MIN_MIN) is True
    assert dominates(worse, better, MIN_MIN) is False


def test_identical_points_do_not_dominate_each_other():
    point = {"a": 1.0, "b": 1.0}
    same = {"a": 1.0, "b": 1.0}
    # No strict improvement anywhere -> neither dominates; both stay on the frontier.
    assert dominates(point, same, MIN_MIN) is False
    assert dominates(same, point, MIN_MIN) is False


def test_incomparable_points_neither_dominates():
    low_a = {"a": 1.0, "b": 4.0}
    low_b = {"a": 4.0, "b": 1.0}
    assert dominates(low_a, low_b, MIN_MIN) is False
    assert dominates(low_b, low_a, MIN_MIN) is False


def test_dominates_respects_mixed_sense():
    # One "max" objective (service) must be read opposite to a "min" one (cost).
    objectives = [("service", "max"), ("cost", "min")]
    better = {"service": 90.0, "cost": 100.0}
    worse = {"service": 80.0, "cost": 100.0}  # equal cost, lower service
    assert dominates(better, worse, objectives) is True
    assert dominates(worse, better, objectives) is False


def test_pareto_frontier_drops_only_the_dominated_point():
    points = {
        "low_a": {"a": 1.0, "b": 4.0},   # non-dominated (extreme on a)
        "balanced": {"a": 2.0, "b": 2.0},  # non-dominated
        "low_b": {"a": 4.0, "b": 1.0},   # non-dominated (extreme on b)
        "interior": {"a": 3.0, "b": 3.0},  # dominated by "balanced"
    }
    assert pareto_frontier(points, MIN_MIN) == ["balanced", "low_a", "low_b"]


def test_pareto_frontier_mixed_sense_with_real_objectives():
    points = {
        "high_service": {
            "service_level_full_pct": 90.0,
            "total_emissions_kgco2e": 100.0,
            "landfill_volume_m3": 50.0,
            "total_system_cost": 200.0,
        },
        "cheap": {
            "service_level_full_pct": 50.0,
            "total_emissions_kgco2e": 200.0,
            "landfill_volume_m3": 80.0,
            "total_system_cost": 100.0,  # only this beats high_service -> non-dominated
        },
        "loser": {
            "service_level_full_pct": 40.0,
            "total_emissions_kgco2e": 300.0,
            "landfill_volume_m3": 90.0,
            "total_system_cost": 300.0,  # worse on every objective -> dominated
        },
    }
    assert pareto_frontier(points, OBJECTIVES) == ["cheap", "high_service"]


# --- dataset reader / report ----------------------------------------------

def test_read_objective_point_pulls_the_means(tmp_path):
    _write_summary(
        tmp_path,
        {
            "service_level_full_pct": 67.38,
            "total_emissions_kgco2e": 2.65e7,
            "landfill_volume_m3": 122158.0,
            "total_system_cost": 1.71e7,
            "collection_rate_pct": 59.38,  # extra row -> ignored
        },
    )
    point = read_objective_point(tmp_path / "summary.csv")
    assert point == {
        "service_level_full_pct": 67.38,
        "total_emissions_kgco2e": 2.65e7,
        "landfill_volume_m3": 122158.0,
        "total_system_cost": 1.71e7,
    }


def test_build_pareto_report_scenario_mode_flags_non_dominated(tmp_path):
    # Two combos: one dominates the other on every objective.
    _write_summary(
        tmp_path / "push__on_demand",
        {
            "service_level_full_pct": 90.0,
            "total_emissions_kgco2e": 100.0,
            "landfill_volume_m3": 50.0,
            "total_system_cost": 200.0,
        },
    )
    _write_summary(
        tmp_path / "pull__on_demand",
        {
            "service_level_full_pct": 40.0,
            "total_emissions_kgco2e": 300.0,
            "landfill_volume_m3": 90.0,
            "total_system_cost": 300.0,
        },
    )
    rows = build_pareto_report(tmp_path)
    flags = {row["config"]: row["non_dominated"] for row in rows}
    assert flags == {"push__on_demand": True, "pull__on_demand": False}


def test_write_pareto_report_round_trips_and_labels_root_mode(tmp_path):
    # Root layout: scenario dirs -> combo dirs. Labels become scenario__combo.
    _write_summary(
        tmp_path / "Baseline" / "push__on_demand",
        {
            "service_level_full_pct": 90.0,
            "total_emissions_kgco2e": 100.0,
            "landfill_volume_m3": 50.0,
            "total_system_cost": 200.0,
        },
    )
    _write_summary(
        tmp_path / "Buffer4wk" / "push__on_demand",
        {
            "service_level_full_pct": 95.0,
            "total_emissions_kgco2e": 90.0,
            "landfill_volume_m3": 40.0,
            "total_system_cost": 180.0,  # dominates the Baseline point on all four
        },
    )
    report = write_pareto_report(tmp_path, root=True)
    assert report == tmp_path / "pareto_frontier.csv"
    contents = report.read_text(encoding="utf-8")
    header, *data_lines = contents.splitlines()
    assert header == (
        "config,service_level_full_pct,total_emissions_kgco2e,"
        "landfill_volume_m3,total_system_cost,non_dominated"
    )
    flags = {line.split(",")[0]: line.split(",")[-1] for line in data_lines}
    assert flags == {
        "Baseline__push__on_demand": "False",
        "Buffer4wk__push__on_demand": "True",
    }


def test_build_pareto_report_empty_dir_returns_no_rows(tmp_path):
    assert build_pareto_report(tmp_path) == []
    assert write_pareto_report(tmp_path) is None
