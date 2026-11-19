"""Tests for the raw-monitor JSON encoder (persistence/serialization.py).

Locks in the property that makes the raw_NNN.json sidecar possible: Enum
members are rewritten to their ``.value`` wherever they appear, INCLUDING as
dict keys -- the case plain ``json.dump(default=str)`` cannot handle.
"""
import json

from models.enums import OutputType, WasteType
from persistence.serialization import build_raw_payload, jsonify


def test_enum_values_rewritten_to_value():
    assert jsonify(OutputType.MDF) == "mdf"
    assert jsonify([WasteType.WOOD_19_12_07, OutputType.OSB]) == ["19 12 07", "osb"]


def test_nested_mixed_keys_and_values():
    data = {"gen1": {WasteType.WOOD_19_12_07: {"series": [1, 2, OutputType.OSB]}}}
    out = jsonify(data)
    assert out == {"gen1": {"19 12 07": {"series": [1, 2, "osb"]}}}
    json.dumps(out)  # whole structure must round-trip


def test_tuples_become_lists():
    assert jsonify((WasteType.WOOD_19_12_07, 3)) == ["19 12 07", 3]


def test_non_enum_leaves_pass_through_unchanged():
    data = {"name": "gen1", "vals": [1, 2.5, None, True]}
    assert jsonify(data) == data


def test_build_raw_payload_output_is_json_serializable_after_jsonify():
    monitor_data = {
        "generation_history": {"gen1": {WasteType.WOOD_19_12_07: [1.0, 2.0]}},
        "consumption_events": [{"product": OutputType.MDF, "consumed": 3.0}],
    }
    reloaded = json.loads(json.dumps(jsonify(build_raw_payload(monitor_data))))

    assert reloaded["generation_history"] == {"gen1": {"19 12 07": [1.0, 2.0]}}
    assert reloaded["consumption_events"] == [{"product": "mdf", "consumed": 3.0}]
