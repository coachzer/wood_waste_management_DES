"""Regression test for the summary-dashboard "Event Cost" panel (VIZ-REVIEW T1).

Failure mode guarded: ``create_summary_dashboard`` read the non-existent key
``event_history['total_cost']['values']``, so the Event Cost panel was
permanently 0 regardless of the recorded overflow cost. The recorded schema is
``event_history['system_events']['total_costs']`` -- a list of per-event cost
increments -- summed exactly as ``create_cost_impact_comparison`` does.

Non-vacuity: with all other metrics zero (empty histories), the distinctive
summed value appears as a bar label in the dashboard HTML only when the correct
key is read; the pre-fix dead-key path (always 0) makes the assertion red.
"""

from visualization.summary_visualization import create_summary_dashboard


def _result_with_overflow_costs(total_costs):
    """A minimal result whose only non-empty event stream is overflow cost."""
    return {
        "inventory_policy": "push",
        "stock_strategy": "on_demand",
        "monitor_data": {
            "generation_history": {},
            "collection_history": {},
            "processing_history": {},
            "event_history": {"system_events": {"total_costs": total_costs}},
        },
    }


def _dashboard_html(output_dir):
    return (output_dir / "summary_dashboard.html").read_text(encoding="utf-8")


def test_event_cost_sums_system_event_increments(tmp_path):
    # Increments sum to 612345.0 -- a value no zero-valued metric can produce,
    # and the dashboard renders each bar's value via an f"{val:.1f}" label.
    create_summary_dashboard(
        [_result_with_overflow_costs([12000.0, 345.0, 600000.0])], str(tmp_path)
    )
    assert "612345.0" in _dashboard_html(tmp_path)


def test_empty_overflow_stream_does_not_crash(tmp_path):
    # An empty stream must read 0 without raising -- guards the fix's gap handling.
    create_summary_dashboard([_result_with_overflow_costs([])], str(tmp_path))
    assert (tmp_path / "summary_dashboard.html").exists()
