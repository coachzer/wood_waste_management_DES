"""Smoke test for the Pareto frontier figure (Matplotlib PDF).

Confirms that ``write_pareto_plot`` produces a ``pareto_frontier.pdf`` beside
a tmp dataset. Plot aesthetics are not asserted -- only that the artifact is
written and non-trivial.
"""
from visualization.pareto_visualization import write_pareto_plot


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


def test_write_pareto_plot_emits_pdf(tmp_path, write_summary):
    _baseline_dataset(write_summary, tmp_path)
    plot_path = write_pareto_plot(tmp_path)
    assert plot_path == tmp_path / "pareto_frontier.pdf"
    assert plot_path.exists()
    assert plot_path.stat().st_size > 0


def test_write_pareto_plot_empty_dir_returns_none(tmp_path):
    assert write_pareto_plot(tmp_path) is None


def test_pareto_figure_2d_polyline_excludes_2d_dominated_4d_frontier_points():
    import matplotlib.pyplot as plt
    from visualization.pareto_visualization import build_pareto_figure

    # All 3 points are 4D-frontier, but mid_cost_win is 2D-dominated by low_emis
    # (low_emis has higher service AND lower emissions).
    points = [
        {
            "label": "push__on_demand",
            "policy": "push",
            "strategy": "on_demand",
            "frontier": True,
            "service": 80.0,
            "service_err": [[1.0], [1.0]],
            "emissions": 5.0,
            "emissions_err": [[0.2], [0.2]],
            "landfill": 100.0,
            "cost": 500.0,
        },
        {
            "label": "pull__reorder_50",
            "policy": "pull",
            "strategy": "reorder_50",
            "frontier": True,
            "service": 75.0,
            "service_err": [[1.0], [1.0]],
            "emissions": 8.0,
            "emissions_err": [[0.2], [0.2]],
            "landfill": 50.0,
            "cost": 200.0,
        },
        {
            "label": "push__reorder_90",
            "policy": "push",
            "strategy": "reorder_90",
            "frontier": True,
            "service": 90.0,
            "service_err": [[1.0], [1.0]],
            "emissions": 10.0,
            "emissions_err": [[0.2], [0.2]],
            "landfill": 20.0,
            "cost": 800.0,
        },
    ]
    fig = build_pareto_figure(points)
    try:
        ax = fig.axes[0]
        frontier_lines = [
            list(line.get_xdata())
            for line in ax.lines
            if line.get_color() == "black" and line.get_linestyle() == "-"
        ]
        assert frontier_lines == [[80.0, 90.0]]
        assert "4-objective" in ax.get_title()
    finally:
        plt.close(fig)
