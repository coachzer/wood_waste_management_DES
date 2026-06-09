"""Tests for the policy-comparison figure's data-extraction core.

The rendering is Matplotlib and not meaningfully assertable, so these exercise
the pure data path that decides where each point lands and how big its 95% CI
crosshairs are: ``read_metric_intervals`` (mean + CI bounds), ``_split_combo_label``
(policy/strategy from the dir name), and ``build_points`` (the asymmetric error
half-widths and the kg->kt emissions scaling). Synthetic tmp summary.csv fixtures,
no simulation -- mirrors ``test_pareto.py``.

Failure modes guarded:
- a swapped CI bound or a dropped kt scaling silently mislocates a crosshair;
- a missing metric silently drops a configuration from the figure;
- a malformed combo dir name silently mis-styles (or mis-places) a point.
"""

import pytest

from visualization.policy_comparison_figure import (
    EMISSIONS_METRIC,
    SERVICE_METRIC,
    _split_combo_label,
    build_points,
    read_metric_intervals,
    write_policy_comparison_figure,
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


def test_read_metric_intervals_returns_mean_and_ci_bounds(tmp_path):
    _write_summary(tmp_path, {SERVICE_METRIC: (70.0, 68.0, 73.0)})
    intervals = read_metric_intervals(tmp_path / "summary.csv", [SERVICE_METRIC])
    # (mean, ci95_low, ci95_high) in that order -- a swap here would invert crosshairs.
    assert intervals[SERVICE_METRIC] == (70.0, 68.0, 73.0)


def test_read_metric_intervals_raises_on_missing_metric(tmp_path):
    # Only service is present; asking for emissions too must fail loudly, not
    # silently drop the configuration from the figure.
    _write_summary(tmp_path, {SERVICE_METRIC: (70.0, 68.0, 73.0)})
    with pytest.raises(KeyError):
        read_metric_intervals(
            tmp_path / "summary.csv", [SERVICE_METRIC, EMISSIONS_METRIC]
        )


def test_split_combo_label_parses_policy_and_strategy():
    assert _split_combo_label("push__on_demand") == ("push", "on_demand")
    assert _split_combo_label("pull__reorder_90") == ("pull", "reorder_90")


def test_split_combo_label_rejects_non_combo_name():
    # A directory that is not exactly one '__' join must raise, not mis-style.
    with pytest.raises(ValueError):
        _split_combo_label("baseline_only")


def test_build_points_computes_asymmetric_err_and_kt_scaling(tmp_path):
    # service: mean 70, CI [68, 73] -> low half-width 2, high half-width 3.
    # emissions: mean 2e6 kg, CI [1e6, 2.5e6] -> 2.0 kt, half-widths 1.0 and 0.5 kt.
    _write_summary(
        tmp_path / "push__reorder_50",
        {
            SERVICE_METRIC: (70.0, 68.0, 73.0),
            EMISSIONS_METRIC: (2_000_000.0, 1_000_000.0, 2_500_000.0),
        },
    )
    (point,) = build_points(tmp_path)

    assert point["policy"] == "push"
    assert point["strategy"] == "reorder_50"
    assert point["service"] == 70.0
    # Asymmetric: [[mean-low], [high-mean]] -- swapping would tilt the crosshair.
    assert point["service_err"] == [[2.0], [3.0]]
    # kg -> kt scaling applied to both the point and its error half-widths.
    assert point["emissions"] == 2.0
    assert point["emissions_err"] == [[1.0], [0.5]]


def test_build_points_empty_when_no_summaries(tmp_path):
    assert build_points(tmp_path) == []


def test_write_figure_returns_none_without_data(tmp_path):
    # No summary.csv anywhere -> no figure, signalled by None (not an empty PDF).
    assert write_policy_comparison_figure(tmp_path) is None


def test_write_figure_emits_nonempty_pdf(tmp_path):
    _write_summary(
        tmp_path / "pull__on_demand",
        {
            SERVICE_METRIC: (53.0, 51.0, 55.0),
            EMISSIONS_METRIC: (1_200_000.0, 1_000_000.0, 1_400_000.0),
        },
    )
    written = write_policy_comparison_figure(tmp_path)
    assert written is not None
    assert written.name == "policy_comparison.pdf"
    assert written.read_bytes().startswith(b"%PDF")
