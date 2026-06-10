"""Tests for entity availability metrics (cleanup task #61).

Exercises analysis.availability against synthetic entity_status_history dicts
in the shape HistoryStore.ensure_entity_status authors -- per-category,
per-entity ``{"timestamps": [...], "status": [...]}`` with status-name strings.
Mirrors the inline-synthetic-dict style of test_avoided_emissions.py -- no
simulation run.
"""

import pytest

from analysis.availability import availability_metrics


def make_monitor_data(generators=None, collectors=None, treatments=None):
    def category(entries):
        return {
            name: {"timestamps": list(range(len(statuses))), "status": list(statuses)}
            for name, statuses in (entries or {}).items()
        }

    return {
        "entity_status_history": {
            "generators": category(generators),
            "collectors": category(collectors),
            "treatments": category(treatments),
        }
    }


def test_pooled_share_of_operational_samples():
    md = make_monitor_data(
        generators={"gen_a": ["OPERATIONAL", "FAILED", "RECOVERING", "OPERATIONAL"]}
    )
    m = availability_metrics(md)
    # 2 of 4 samples OPERATIONAL; FAILED and RECOVERING both count as downtime.
    assert m["availability_generator_pct"] == pytest.approx(50.0)


def test_pooling_weights_entities_by_sample_count():
    md = make_monitor_data(
        collectors={
            "col_a": ["OPERATIONAL"] * 9,
            "col_b": ["FAILED"],
        }
    )
    m = availability_metrics(md)
    # Pooled over samples (9 of 10), not a mean of per-entity rates (50%).
    assert m["availability_collector_pct"] == pytest.approx(90.0)


def test_echelons_are_independent_and_system_pools_all_samples():
    md = make_monitor_data(
        generators={"gen_a": ["OPERATIONAL", "OPERATIONAL"]},
        collectors={"col_a": ["FAILED", "FAILED"]},
        treatments={"trt_a": ["OPERATIONAL", "FAILED"]},
    )
    m = availability_metrics(md)
    assert m["availability_generator_pct"] == pytest.approx(100.0)
    assert m["availability_collector_pct"] == pytest.approx(0.0)
    assert m["availability_treatment_pct"] == pytest.approx(50.0)
    assert m["availability_system_pct"] == pytest.approx(50.0)


def test_no_samples_is_none_not_zero():
    m = availability_metrics(make_monitor_data())
    assert m["availability_generator_pct"] is None
    assert m["availability_collector_pct"] is None
    assert m["availability_treatment_pct"] is None
    assert m["availability_system_pct"] is None


def test_missing_history_key_is_all_none():
    m = availability_metrics({})
    assert all(value is None for value in m.values())
