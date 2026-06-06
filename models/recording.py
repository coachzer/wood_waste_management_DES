"""Recording interface the domain layer depends on.

``models/`` must not import the recording layer (the ``monitoring`` package or the
``instrumentation`` space the concrete recorders moved to). A domain model importing
the concrete ``WasteMonitor`` inverts the layer dependency and closes the
circular import that forces the "run by file path, not ``-m``" workaround and the
conftest import-priming (see HANDOFF.md / CLAUDE.md).

This Protocol is the only recording-facing contract the domain layer sees. The
composition root (``SimulationManager`` -> ``FacilityBuilder``) injects a concrete
recorder satisfying it -- in production ``instrumentation.waste_monitor.WasteMonitor``
-- into each ``OperationalEntity``. The domain layer calls only the methods
declared here; keep this surface minimal.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EntityStatusRecorder(Protocol):
    """Minimal recorder the domain layer calls during failure-state transitions."""

    def record_entity_status(self, entity, timestamp: float) -> None:
        """Record an entity's status at a transition moment (e.g. failure/recovery)."""
        ...
