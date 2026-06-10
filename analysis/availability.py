"""Entity availability from the status history (cleanup task #61).

A post-hoc accounting metric: the fraction of polled status samples in which an
entity was OPERATIONAL, pooled per echelon and system-wide. The status history
(``entity_status_history``) is sampled on the monitor's fixed polling cadence,
so the sample share approximates the time share -- no per-interval weighting is
needed. This is the first consumer of ``entity_status_history``; before it, the
history was written and exported but fed no KPI.

Reported as percentages under the ``availability`` namespace so the metric
rides the generic MC aggregation + CRN machinery (issues 06/07). ``None`` when
an echelon has no samples (undefined, not zero), matching the service-level
convention.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Status-history category key per echelon, in reporting order.
_ECHELON_CATEGORIES = (
    ("generator", "generators"),
    ("collector", "collectors"),
    ("treatment", "treatments"),
)

_OPERATIONAL = "OPERATIONAL"


def _pooled_availability(category_history: Dict[str, Any]) -> Optional[float]:
    """Percent of status samples that are OPERATIONAL, pooled across entities."""
    operational = 0
    total = 0
    for entity_history in category_history.values():
        statuses = entity_history.get("status", [])
        total += len(statuses)
        operational += sum(1 for status in statuses if status == _OPERATIONAL)
    if total == 0:
        return None
    return operational / total * 100.0


def availability_metrics(monitor_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Pooled OPERATIONAL-time percentage per echelon and system-wide.

    Keys are ``availability_{echelon}_pct`` for generator/collector/treatment,
    then ``availability_system_pct`` (pooled over every sample of every entity,
    so heavily-polled echelons weigh proportionally).
    """
    status_history = monitor_data.get("entity_status_history", {})
    metrics: Dict[str, Optional[float]] = {}
    all_entities: Dict[str, Any] = {}
    for echelon, category in _ECHELON_CATEGORIES:
        category_history = status_history.get(category, {})
        metrics[f"availability_{echelon}_pct"] = _pooled_availability(category_history)
        for entity_name, entity_history in category_history.items():
            all_entities[f"{category}/{entity_name}"] = entity_history
    metrics["availability_system_pct"] = _pooled_availability(all_entities)
    return metrics
