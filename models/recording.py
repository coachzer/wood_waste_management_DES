"""Recording interface the domain layer depends on.

``models/`` must not import the recording layer (``instrumentation``): a domain
model naming the concrete ``WasteMonitor`` re-closes the circular import (see
CLAUDE.md). Instead the composition root injects a concrete recorder satisfying
this Protocol -- in production ``instrumentation.waste_monitor.WasteMonitor`` --
into each ``OperationalEntity``. Keep this surface minimal.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EntityStatusRecorder(Protocol):
    """Minimal recorder the domain layer calls during failure-state transitions."""

    def record_entity_status(self, entity, timestamp: float) -> None:
        """Record an entity's status at a transition moment (e.g. failure/recovery)."""
        ...
