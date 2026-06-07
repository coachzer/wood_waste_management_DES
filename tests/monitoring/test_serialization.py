"""Tests for the raw-monitor JSON encoder (persistence/serialization.py).

Locks in the property that makes the raw_NNN.json sidecar possible: Enum
members are rewritten to their ``.value`` wherever they appear, INCLUDING as
dict keys -- the case plain ``json.dump(default=str)`` cannot handle.
"""
import json

import pytest

from models.enums import OutputType, WasteType
from persistence.serialization import RAW_PAYLOAD_KEYS, build_raw_payload, jsonify


def test_enum_dict_keys_rewritten_to_value():
    out = jsonify({WasteType.CONSTRUCTION_WOOD_17_02_01: 5.0})
    assert out == {"17 02 01": 5.0}
    json.dumps(out)  # must not raise


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


def test_default_str_alone_cannot_serialize_enum_keys():
    """Documents WHY jsonify exists: json's default= never fires for dict keys."""
    with pytest.raises(TypeError):
        json.dumps({WasteType.WOOD_19_12_07: 1}, default=str)


def test_build_raw_payload_selects_only_history_and_event_logs():
    monitor_data = {key: {"present": key} for key in RAW_PAYLOAD_KEYS}
    monitor_data["final_summary"] = {"dropped": True}
    monitor_data["storage_capacities"] = {"dropped": True}

    payload = build_raw_payload(monitor_data)

    assert set(payload) == set(RAW_PAYLOAD_KEYS)
    assert "final_summary" not in payload
    assert "storage_capacities" not in payload


def test_build_raw_payload_output_is_json_serializable_after_jsonify():
    monitor_data = {
        "generation_history": {"gen1": {WasteType.WOOD_19_12_07: [1.0, 2.0]}},
        "consumption_events": [{"product": OutputType.MDF, "consumed": 3.0}],
    }
    encoded = jsonify(build_raw_payload(monitor_data))
    text = json.dumps(encoded)
    assert "19 12 07" in text and "mdf" in text
