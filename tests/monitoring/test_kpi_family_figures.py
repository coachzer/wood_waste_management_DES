"""Tests for the bullwhip/residence/carbon KPI-family figures' data core.

Mirrors ``test_policy_comparison_figure.py``: the rendering is Matplotlib and
not meaningfully assertable, so these exercise the pure data path — which combo
gets which mean/CI triple for which metric, and the kg->kt scaling — plus a
nonempty-PDF smoke per figure. Synthetic tmp summary.csv fixtures, no simulation.

Failure modes guarded:
- a combo silently dropped (or mis-styled) from a family figure;
- a missing metric silently rendering as zero instead of failing loudly;
- a dropped kt scaling putting carbon bars three orders of magnitude off.
"""

import pytest

from visualization.kpi_family_figures import (
    BULLWHIP_FLOOR_METRIC,
    BULLWHIP_RATIO_METRICS,
    CARBON_METRICS,
    RESIDENCE_METRICS,
    build_metric_table,
    to_kilotonnes,
    write_bullwhip_figure,
    write_carbon_figure,
    write_residence_figure,
)


def _write_summary(combo_dir, rows):
    """Write a summary.csv (real header + a row per metric) under combo_dir.

    ``rows`` maps metric -> (mean, ci95_low, ci95_high); stdev/count are filler.
    """
    combo_dir.mkdir(parents=True, exist_ok=True)
    lines = ["metric,mean,stdev,ci95_low,ci95_high,count"]
    for metric, (mean, low, high) in rows.items():
        lines.append(f"{metric},{mean},0,{low},{high},100")
    (combo_dir / "summary.csv").write_text("\n".join(lines), encoding="utf-8")


def test_build_metric_table_one_row_per_combo_with_intervals(tmp_path):
    _write_summary(
        tmp_path / "push__reorder_50",
        {"bullwhip.treatment_anchored": (980.0, 900.0, 1060.0)},
    )
    _write_summary(
        tmp_path / "pull__on_demand",
        {"bullwhip.treatment_anchored": (240.0, 200.0, 280.0)},
    )

    table = build_metric_table(tmp_path, ["bullwhip.treatment_anchored"])

    # Sorted by combo label (pull before push) for a deterministic draw order.
    assert [row["label"] for row in table] == ["pull__on_demand", "push__reorder_50"]
    pull_row, push_row = table
    assert pull_row["policy"] == "pull"
    assert pull_row["strategy"] == "on_demand"
    assert pull_row["values"]["bullwhip.treatment_anchored"] == (240.0, 200.0, 280.0)
    assert push_row["policy"] == "push"
    assert push_row["values"]["bullwhip.treatment_anchored"] == (980.0, 900.0, 1060.0)


def test_build_metric_table_raises_on_missing_metric(tmp_path):
    # A combo whose summary.csv lacks a requested family key must fail loudly,
    # not render that combo as zero (or drop it) in the figure.
    _write_summary(
        tmp_path / "push__on_demand",
        {"bullwhip.treatment_anchored": (980.0, 900.0, 1060.0)},
    )
    with pytest.raises(KeyError):
        build_metric_table(
            tmp_path,
            ["bullwhip.treatment_anchored", "bullwhip.collector_anchored"],
        )


def test_build_metric_table_empty_when_no_summaries(tmp_path):
    assert build_metric_table(tmp_path, ["bullwhip.treatment_anchored"]) == []


def _bullwhip_rows(scale=1.0):
    """All seven bullwhip keys with distinct, plausible (mean, low, high) rows."""
    rows = {}
    for index, metric in enumerate(BULLWHIP_RATIO_METRICS):
        mean = (index + 1) * 10.0 * scale
        rows[metric] = (mean, mean * 0.9, mean * 1.1)
    rows[BULLWHIP_FLOOR_METRIC] = (0.025, 0.024, 0.026)
    return rows


def test_write_bullwhip_figure_returns_none_without_data(tmp_path):
    assert write_bullwhip_figure(tmp_path) is None


def test_write_bullwhip_figure_emits_nonempty_pdf(tmp_path):
    _write_summary(tmp_path / "push__on_demand", _bullwhip_rows())
    _write_summary(tmp_path / "pull__reorder_90", _bullwhip_rows(scale=0.5))
    written = write_bullwhip_figure(tmp_path)
    assert written is not None
    assert written.name == "bullwhip_comparison.pdf"
    assert written.read_bytes().startswith(b"%PDF")


def _residence_rows():
    """The four per-stage residence-days keys with distinct plausible rows."""
    return {
        metric: ((index + 1) * 100.0, (index + 1) * 90.0, (index + 1) * 110.0)
        for index, metric in enumerate(RESIDENCE_METRICS)
    }


def test_write_residence_figure_returns_none_without_data(tmp_path):
    assert write_residence_figure(tmp_path) is None


def test_write_residence_figure_emits_nonempty_pdf(tmp_path):
    _write_summary(tmp_path / "push__reorder_50", _residence_rows())
    _write_summary(tmp_path / "pull__on_demand", _residence_rows())
    written = write_residence_figure(tmp_path)
    assert written is not None
    assert written.name == "residence_comparison.pdf"
    assert written.read_bytes().startswith(b"%PDF")


def test_to_kilotonnes_scales_whole_interval():
    # kg -> kt on mean and both CI bounds; a sign must survive the scaling
    # (biogenic carbon stored is negative = sequestered).
    assert to_kilotonnes((2_000_000.0, 1_000_000.0, 2_500_000.0)) == (2.0, 1.0, 2.5)
    assert to_kilotonnes((-4_000_000.0, -5_000_000.0, -3_000_000.0)) == (
        -4.0,
        -5.0,
        -3.0,
    )


def _carbon_rows():
    """The three orthogonal carbon lines: operational +, avoided +, biogenic -."""
    return {
        "total_emissions_kgco2e": (24_000_000.0, 22_000_000.0, 26_000_000.0),
        "carbon.avoided_emissions_total_kgco2e": (
            30_000_000.0,
            29_000_000.0,
            31_000_000.0,
        ),
        "carbon.biogenic_carbon_stored_total_kgco2e": (
            -53_000_000.0,
            -55_000_000.0,
            -51_000_000.0,
        ),
    }


def test_carbon_metrics_are_the_three_orthogonal_lines():
    # ADR 0011: operational, avoided, biogenic — side by side, never netted.
    # A fourth (netted) metric appearing here is a modelling violation.
    assert CARBON_METRICS == [
        "total_emissions_kgco2e",
        "carbon.avoided_emissions_total_kgco2e",
        "carbon.biogenic_carbon_stored_total_kgco2e",
    ]


def test_write_carbon_figure_returns_none_without_data(tmp_path):
    assert write_carbon_figure(tmp_path) is None


def test_write_carbon_figure_emits_nonempty_pdf(tmp_path):
    _write_summary(tmp_path / "push__on_demand", _carbon_rows())
    _write_summary(tmp_path / "pull__reorder_50", _carbon_rows())
    written = write_carbon_figure(tmp_path)
    assert written is not None
    assert written.name == "carbon_comparison.pdf"
    assert written.read_bytes().startswith(b"%PDF")
