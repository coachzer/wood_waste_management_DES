"""JSON serialization for raw monitor data with Enum keys.

The per-run history dicts carry ``WasteType``/``OutputType`` members as dict
KEYS (e.g. per-waste-type breakdowns inside ``generation_history``). Plain
``json.dump`` cannot serialize those, and its ``default=`` hook does NOT help:
``default=`` fires for VALUES only, never for dict keys, and ``WasteType`` is a
plain ``Enum`` (no ``str`` mixin).

``jsonify`` walks the structure and rewrites every ``Enum`` member to its
``.value`` wherever it appears -- as a dict key, a dict value, or inside a
list/tuple -- yielding a structure ``json.dump`` accepts. ``build_raw_payload``
selects every block ``extract_kpis`` consumes in process, so they can be
persisted as an additive ``raw_NNN.json`` sidecar.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from instrumentation.history_store import HISTORY_KEYS

# Every monitor_data block extract_kpis reads. Persisting them lets a new KPI
# be computed without a re-run.
RAW_PAYLOAD_KEYS = HISTORY_KEYS + (
    "transport_flows",
    "consumption_events",
    "storage_capacities",
    "final_summary",
)


def jsonify(obj: Any) -> Any:
    """Return a JSON-serializable copy of ``obj`` with Enums rewritten to ``.value``.

    Recurses through dicts (rewriting both keys and values), lists, and tuples.
    Enum members become their ``.value``; every other leaf is returned as-is.
    This is the only correct way to serialize the Enum-KEYED history dicts:
    ``json``'s ``default=`` hook never fires for dict keys, so a recursive
    rewrite is required rather than a value-only encoder.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {jsonify(key): jsonify(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonify(item) for item in obj]
    return obj


def build_raw_payload(monitor_data: Dict[str, Any]) -> Dict[str, Any]:
    """Select the raw history dicts and event logs from ``monitor_data``.

    Returns every block under ``RAW_PAYLOAD_KEYS``, so ``extract_kpis`` on the
    reloaded sidecar matches the live run. The result still contains Enum
    keys/values; pass it through ``jsonify`` before ``json.dump``.
    """
    return {key: monitor_data.get(key, {}) for key in RAW_PAYLOAD_KEYS}
