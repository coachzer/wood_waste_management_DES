"""Outlet waste split by where SURS sends each code (ADR 0036).

The simulation does not route outlet waste. This applies the SURS destination
shares from ``data/outlet_destination_shares.json`` to each code's outlet volume
at reporting time.
"""
import json
from pathlib import Path
from typing import Any, Dict

OUTLET_SHARES_PATH = Path(__file__).resolve().parent.parent / "data" / "outlet_destination_shares.json"
OUTLET_DESTINATIONS = ["recycling", "energy_recovery", "other_recovery", "disposal"]


def _code(waste_type: Any) -> str:
    return getattr(waste_type, "value", waste_type)


def outlet_volume_by_code(generation_history: Dict[str, Any]) -> Dict[str, float]:
    volume_by_code: Dict[str, float] = {}
    for history in generation_history.values():
        for waste_type, series in history.get("total_outlet", {}).items():
            if isinstance(series, list) and series:
                code = _code(waste_type)
                volume_by_code[code] = volume_by_code.get(code, 0.0) + float(series[-1])
    return volume_by_code


def outlet_destination_metrics(generation_history: Dict[str, Any]) -> Dict[str, float]:
    """Outlet m3 per SURS destination. A code with no SURS shares counts as other recovery."""
    shares_by_code = json.loads(OUTLET_SHARES_PATH.read_text())
    metrics = {f"{destination}_m3": 0.0 for destination in OUTLET_DESTINATIONS}
    for code, volume in sorted(outlet_volume_by_code(generation_history).items()):
        shares = shares_by_code.get(code) or {"other_recovery": 1.0}
        for destination, share in shares.items():
            metrics[f"{destination}_m3"] += volume * share
    return metrics
