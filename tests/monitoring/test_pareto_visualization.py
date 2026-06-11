"""Smoke test for the Pareto frontier figure (Matplotlib PDF).

Confirms that ``build_pareto_figure`` returns a Matplotlib Figure and that
``write_pareto_plot`` produces a ``pareto_frontier.pdf`` beside a tmp
dataset. Plot aesthetics are not asserted -- only that the artifact is
written and non-trivial.
"""

import matplotlib.pyplot as plt

from visualization.pareto_visualization import (
    build_pareto_figure,
    write_pareto_plot,
)


def _baseline_dataset(write_summary, scenario_dir):
    write_summary(
        scenario_dir / "push__reorder_50",
        {
            "service_level_full_pct": 74.96,
            "total_emissions_kgco2e": 8.55e6,
            "landfill_volume_m3": 34129.6,
            "total_system_cost": 1.52e7,
        },
    )
    write_summary(
        scenario_dir / "push__on_demand",
        {
            "service_level_full_pct": 67.38,
            "total_emissions_kgco2e": 2.65e7,
            "landfill_volume_m3": 122158.0,
            "total_system_cost": 1.72e7,
        },
    )


def test_build_pareto_figure_returns_matplotlib_figure(tmp_path, write_summary):
    _baseline_dataset(write_summary, tmp_path)
    from visualization.pareto_visualization import _build_points
    from analysis.pareto import OBJECTIVES

    points = _build_points(tmp_path, root=False, objectives=OBJECTIVES)
    fig = build_pareto_figure(points)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_write_pareto_plot_emits_pdf(tmp_path, write_summary):
    _baseline_dataset(write_summary, tmp_path)
    plot_path = write_pareto_plot(tmp_path)
    assert plot_path == tmp_path / "pareto_frontier.pdf"
    assert plot_path.exists()
    assert plot_path.stat().st_size > 0


def test_write_pareto_plot_empty_dir_returns_none(tmp_path):
    assert write_pareto_plot(tmp_path) is None
