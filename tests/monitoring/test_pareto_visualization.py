"""Smoke test for the Pareto parallel-coordinates plot (C5 follow-up).

Confirms the figure builds from report rows and that ``write_pareto_plot``
produces an ``pareto_frontier.html`` beside a tmp dataset. Plot aesthetics are
not asserted -- only that the artifact is written and non-trivial.
"""

from monitoring.pareto import build_pareto_report
from monitoring.visualization.pareto_visualization import (
    build_pareto_figure,
    write_pareto_plot,
)


def _write_summary(combo_dir, means):
    combo_dir.mkdir(parents=True, exist_ok=True)
    lines = ["metric,mean,stdev,ci95_low,ci95_high,count"]
    for metric, mean in means.items():
        lines.append(f"{metric},{mean},0,0,0,10")
    (combo_dir / "summary.csv").write_text("\n".join(lines), encoding="utf-8")


def _baseline_dataset(scenario_dir):
    _write_summary(
        scenario_dir / "push__reorder_50",
        {
            "service_level_full_pct": 74.96,
            "total_emissions_kgco2e": 8.55e6,
            "landfill_volume_m3": 34129.6,
            "total_system_cost": 1.52e7,
        },
    )
    _write_summary(
        scenario_dir / "push__on_demand",
        {
            "service_level_full_pct": 67.38,
            "total_emissions_kgco2e": 2.65e7,
            "landfill_volume_m3": 122158.0,
            "total_system_cost": 1.72e7,
        },
    )


def test_build_pareto_figure_has_config_and_objective_axes(tmp_path):
    _baseline_dataset(tmp_path)
    rows = build_pareto_report(tmp_path)
    figure = build_pareto_figure(rows)
    dimensions = figure.data[0].dimensions
    labels = [dim["label"] for dim in dimensions]
    # Leading config axis plus one axis per objective.
    assert labels[0] == "config"
    assert len(dimensions) == 1 + 4
    # One polyline value per configuration on every axis.
    assert all(len(dim["values"]) == len(rows) for dim in dimensions)


def test_write_pareto_plot_emits_html(tmp_path):
    _baseline_dataset(tmp_path)
    plot_path = write_pareto_plot(tmp_path)
    assert plot_path == tmp_path / "pareto_frontier.html"
    assert plot_path.exists()
    assert plot_path.stat().st_size > 0


def test_write_pareto_plot_empty_dir_returns_none(tmp_path):
    assert write_pareto_plot(tmp_path) is None
