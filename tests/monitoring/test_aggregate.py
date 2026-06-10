"""Tests for per-combo Monte Carlo summary aggregation (issue 06).

Exercises the pure ``summary_rows`` seam that ``main.py`` writes to
``summary.csv``: marginal-KPI mean/Student-t CIs (ADR 0008), the generic pass
over the ``bullwhip`` namespace, and the None/degenerate handling for both.
"""

import math

from scipy import stats

from analysis.baseline_aggregate import summary_rows


def _row(rows, metric):
    """Return the parsed cells of the row whose first column == ``metric``."""
    for line in rows:
        cells = line.split(",")
        if cells[0] == metric:
            return cells
    return None


def test_header_is_first_row_and_marginal_mean_is_reported():
    kpis = [
        {"total_generated_m3": 100.0, "bullwhip": {}},
        {"total_generated_m3": 200.0, "bullwhip": {}},
    ]
    rows = summary_rows(kpis)
    assert rows[0] == "metric,mean,stdev,ci95_low,ci95_high,count"
    cells = _row(rows, "total_generated_m3")
    assert cells is not None
    assert float(cells[1]) == 150.0
    assert int(cells[5]) == 2


def test_marginal_ci_uses_student_t_not_normal_z():
    # Four reps of a metric: mean 5, sample stdev sqrt(var). The CI half-width
    # must use t(0.975, 3) ~= 3.182, not z = 1.96 (ADR 0008).
    vals = [2.0, 4.0, 6.0, 8.0]
    kpis = [{"total_generated_m3": v, "bullwhip": {}} for v in vals]
    cells = _row(summary_rows(kpis), "total_generated_m3")
    mean = sum(vals) / len(vals)
    stdev = math.sqrt(sum((x - mean) ** 2 for x in vals) / (len(vals) - 1))
    t_margin = float(stats.t.ppf(0.975, len(vals) - 1)) * stdev / math.sqrt(len(vals))
    z_margin = 1.96 * stdev / math.sqrt(len(vals))
    # Cells are formatted to 6 significant figures, so compare at that precision.
    assert math.isclose(float(cells[3]), mean - t_margin, rel_tol=1e-5)
    assert math.isclose(float(cells[4]), mean + t_margin, rel_tol=1e-5)
    # The t interval is materially wider than the old z interval at small n.
    assert (mean + t_margin) - (mean - t_margin) > (mean + z_margin) - (mean - z_margin)


def test_single_replication_collapses_ci_to_the_mean():
    # n=1 has no spread and t.ppf is undefined at zero df: stdev 0, CI == mean.
    cells = _row(summary_rows([{"total_generated_m3": 42.0, "bullwhip": {}}]), "total_generated_m3")
    assert float(cells[1]) == 42.0
    assert float(cells[2]) == 0.0
    assert float(cells[3]) == 42.0
    assert float(cells[4]) == 42.0
    assert int(cells[5]) == 1


def test_marginal_none_values_excluded_and_all_none_metric_skipped():
    kpis = [
        {"service_level_full_pct": 80.0, "service_level_operational_pct": None, "bullwhip": {}},
        {"service_level_full_pct": None, "service_level_operational_pct": None, "bullwhip": {}},
        {"service_level_full_pct": 90.0, "service_level_operational_pct": None, "bullwhip": {}},
    ]
    rows = summary_rows(kpis)
    # Partial-None: mean over the two present values, count == 2.
    present = _row(rows, "service_level_full_pct")
    assert float(present[1]) == 85.0
    assert int(present[5]) == 2
    # All-None marginal metric: no row at all (existing convention).
    assert _row(rows, "service_level_operational_pct") is None


def test_bullwhip_namespace_emitted_as_prefixed_rows_in_authored_order():
    kpis = [
        {"bullwhip": {"treatment_anchored": 2.0, "collector_anchored": 0.8}},
        {"bullwhip": {"treatment_anchored": 4.0, "collector_anchored": 1.2}},
    ]
    rows = summary_rows(kpis)
    treatment = _row(rows, "bullwhip.treatment_anchored")
    collector = _row(rows, "bullwhip.collector_anchored")
    assert float(treatment[1]) == 3.0 and int(treatment[5]) == 2
    assert float(collector[1]) == 1.0 and int(collector[5]) == 2
    # Insertion order preserved: treatment row precedes collector row.
    metrics = [line.split(",")[0] for line in rows]
    assert metrics.index("bullwhip.treatment_anchored") < metrics.index("bullwhip.collector_anchored")


def test_bullwhip_all_none_metric_emits_blank_row_with_zero_count():
    # Degenerate in every replication: row stays present so the key is
    # discoverable, with count 0 and empty stat cells.
    kpis = [
        {"bullwhip": {"collector_anchored": None}},
        {"bullwhip": {"collector_anchored": None}},
    ]
    cells = _row(summary_rows(kpis), "bullwhip.collector_anchored")
    assert cells is not None
    assert cells[1:5] == ["", "", "", ""]
    assert int(cells[5]) == 0


def test_bullwhip_partial_none_excluded_from_mean_with_count():
    # One degenerate replication is dropped from the mean; count reflects the
    # two that contributed.
    kpis = [
        {"bullwhip": {"treatment_anchored": 2.0}},
        {"bullwhip": {"treatment_anchored": None}},
        {"bullwhip": {"treatment_anchored": 4.0}},
    ]
    cells = _row(summary_rows(kpis), "bullwhip.treatment_anchored")
    assert float(cells[1]) == 3.0
    assert int(cells[5]) == 2


def test_arbitrary_new_bullwhip_key_flows_through_without_wiring():
    # The aggregation is generic over the namespace: a key never mentioned in
    # this module still produces a row (acceptance criterion for issue 06).
    kpis = [
        {"bullwhip": {"some_future_echelon_metric": 1.5}},
        {"bullwhip": {"some_future_echelon_metric": 2.5}},
    ]
    cells = _row(summary_rows(kpis), "bullwhip.some_future_echelon_metric")
    assert cells is not None
    assert float(cells[1]) == 2.0
    assert int(cells[5]) == 2


def test_residence_namespace_flows_through_as_prefixed_rows():
    # The second generic namespace (C4) rides the same pass: residence keys are
    # emitted as `residence.{key}` rows with mean + Student-t CI, no extra wiring.
    kpis = [
        {"residence": {"treatment_residence_days": 2.0, "generator_wip_m3": 100.0}},
        {"residence": {"treatment_residence_days": 4.0, "generator_wip_m3": 300.0}},
    ]
    rows = summary_rows(kpis)
    residence = _row(rows, "residence.treatment_residence_days")
    assert residence is not None
    assert float(residence[1]) == 3.0 and int(residence[5]) == 2
    wip = _row(rows, "residence.generator_wip_m3")
    assert wip is not None and float(wip[1]) == 200.0


def test_service_by_product_namespace_emitted_as_prefixed_rows():
    # VIZ-REVIEW T8: the per-product full service level dict rides the same
    # generic pass, so summary.csv carries one row per product with mean + CI.
    kpis = [
        {"service_level_full_by_product_pct": {"mdf": 90.0, "osb": 80.0}},
        {"service_level_full_by_product_pct": {"mdf": 70.0, "osb": 60.0}},
    ]
    rows = summary_rows(kpis)
    mdf = _row(rows, "service_level_full_by_product_pct.mdf")
    assert mdf is not None
    assert float(mdf[1]) == 80.0 and int(mdf[5]) == 2
    osb = _row(rows, "service_level_full_by_product_pct.osb")
    assert osb is not None and float(osb[1]) == 70.0


def test_service_by_product_never_attempted_product_emits_count_zero_row():
    # A product the market never attempted is None in every replication
    # (undefined, not zero); the row stays discoverable with count 0.
    kpis = [
        {"service_level_full_by_product_pct": {"mdf": None}},
        {"service_level_full_by_product_pct": {"mdf": None}},
    ]
    cells = _row(summary_rows(kpis), "service_level_full_by_product_pct.mdf")
    assert cells is not None
    assert int(cells[5]) == 0


def test_residence_none_across_replications_still_emits_discoverable_row():
    # All-None across replications: the row still appears with count 0 so the
    # namespace stays discoverable (mirrors the bullwhip degenerate handling).
    kpis = [
        {"residence": {"treatment_residence_days": None}},
        {"residence": {"treatment_residence_days": None}},
    ]
    cells = _row(summary_rows(kpis), "residence.treatment_residence_days")
    assert cells is not None
    assert int(cells[5]) == 0
