"""Parallel-coordinates visualization of the Pareto frontier (C5 follow-up).

The frontier is a four-objective reduction (service, emissions, landfill, cost)
that a 2D scatter cannot show without dropping axes. A parallel-coordinates plot
puts all four objectives on equal footing -- one vertical axis each, one polyline
per configuration -- and colors the non-dominated lines distinctly from the
dominated ones, so the trade-offs the frontier encodes are visible at a glance.

Every axis is oriented "best at the top" (maximize objectives ascending,
minimize objectives reversed), so a frontier configuration reads as a line that
stays high somewhere no other line beats.

Unlike ``monitoring/pareto.py`` (the pure, project-import-free CSV layer), this
module is a normal project module: it imports the frontier logic from
``monitoring.pareto`` and depends on Plotly, like the other
``monitoring/visualization/*`` modules. It is HTML-only -- no static export, so
no kaleido dependency.
"""

from pathlib import Path
from typing import List, Tuple

import plotly.graph_objects as go

from monitoring.pareto import OBJECTIVES, build_pareto_report

# Human-readable axis names; the direction arrow is derived from the objective
# sense in OBJECTIVES so this stays a pure presentation map.
_AXIS_NAMES = {
    "service_level_full_pct": "Service level %",
    "total_emissions_kgco2e": "Emissions kgCO2e",
    "landfill_volume_m3": "Landfill m3",
    "total_system_cost": "Total cost",
}

# Two-tone color scale keyed by the non_dominated flag (0 -> dominated grey,
# 1 -> frontier red); the continuous scale is fine because only 0 and 1 occur.
_DOMINATED_COLOR = "#c7c7c7"
_FRONTIER_COLOR = "#d62728"


def _axis_label(metric: str, sense: str) -> str:
    name = _AXIS_NAMES.get(metric, metric)
    direction = "higher" if sense == "max" else "lower"
    return f"{name}<br>({direction} better)"


def _axis_range(values: List[float], sense: str) -> List[float]:
    """Best-at-top range: ascending for maximize, reversed for minimize.

    A degenerate (all-equal) objective gets a small symmetric pad so Plotly does
    not draw a zero-width axis.
    """
    low, high = min(values), max(values)
    if low == high:
        low, high = low - 1.0, high + 1.0
    return [low, high] if sense == "max" else [high, low]


def build_pareto_figure(rows: List[dict], objectives: List[Tuple[str, str]] = OBJECTIVES) -> go.Figure:
    """Build the parallel-coordinates figure from ``build_pareto_report`` rows.

    The leading axis is a categorical ``config`` axis (one tick per configuration)
    so each polyline can be traced back to its combo; the remaining axes are the
    objectives, oriented best-at-top. Lines are colored by the ``non_dominated``
    flag.
    """
    labels = [row["config"] for row in rows]
    flags = [1 if row["non_dominated"] else 0 for row in rows]

    dimensions = [
        dict(
            label="config",
            values=list(range(len(rows))),
            tickvals=list(range(len(rows))),
            ticktext=labels,
            range=[-0.5, len(rows) - 0.5],
        )
    ]
    for metric, sense in objectives:
        values = [row[metric] for row in rows]
        dimensions.append(
            dict(
                label=_axis_label(metric, sense),
                values=values,
                range=_axis_range(values, sense),
            )
        )

    figure = go.Figure(
        data=go.Parcoords(
            line=dict(
                color=flags,
                colorscale=[[0.0, _DOMINATED_COLOR], [1.0, _FRONTIER_COLOR]],
                cmin=0,
                cmax=1,
                showscale=True,
                colorbar=dict(
                    tickvals=[0, 1],
                    ticktext=["dominated", "frontier"],
                    title="status",
                    len=0.4,
                ),
            ),
            dimensions=dimensions,
        )
    )
    n_frontier = sum(flags)
    figure.update_layout(
        title=f"Pareto frontier ({n_frontier}/{len(rows)} non-dominated)",
        font=dict(size=12),
    )
    return figure


def write_pareto_plot(
    path,
    root: bool = False,
    objectives: List[Tuple[str, str]] = OBJECTIVES,
):
    """Write ``pareto_frontier.html`` beside the CSV under ``path`` and return its path.

    Re-derives the frontier from the ``summary.csv`` means (via
    ``build_pareto_report``), so it stays consistent with ``pareto_frontier.csv``
    and can regenerate the plot without re-simulating. Returns ``None`` when there
    is nothing to plot (no ``summary.csv`` files under ``path``).
    """
    path = Path(path)
    rows = build_pareto_report(path, root=root, objectives=objectives)
    if not rows:
        return None
    figure = build_pareto_figure(rows, objectives=objectives)
    plot_path = path / "pareto_frontier.html"
    figure.write_html(str(plot_path))
    return plot_path
