"""Import-inversion contract for the monitoring refactor (clean-monitoring issue 02).

The domain layer (``models/``) must NOT import the ``monitoring`` package. A
domain model importing the concrete ``WasteMonitor`` is the inverted edge that
closes the circular import forcing the "run by file path, not ``-m``" workaround
(HANDOFF.md / CLAUDE.md). The fix: ``OperationalEntity`` depends on the
``EntityStatusRecorder`` Protocol and receives a concrete recorder by injection
from the composition root, never constructing one itself.

These tests pin three failure modes:
  1. the inverted import creeping back into ``models/`` (static AST guard);
  2. the base class silently constructing its own recorder again instead of
     using the injected one (behavioral pin);
  3. the concrete ``WasteMonitor`` drifting out of conformance with the contract
     the domain layer calls.

Each assertion was mutation-verified non-vacuous -- see the per-test docstrings
for the exact mutation that turns it red.
"""
import ast
from pathlib import Path

from models.data_classes import OperationalEntity
from models.recording import EntityStatusRecorder

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "models"


def _monitoring_imports_in(path: Path) -> list[str]:
    """Return 'file:line' for every import of the ``monitoring`` package in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT).as_posix()
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "monitoring" or alias.name.startswith("monitoring."):
                    found.append(f"{rel}:{node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # level>0 is a relative import within models/, which can never reach
            # the top-level monitoring package, so only absolute imports matter.
            if node.level == 0 and (module == "monitoring" or module.startswith("monitoring.")):
                found.append(f"{rel}:{node.lineno}")
    return found


def test_models_layer_does_not_import_monitoring():
    """The domain layer must not name the monitoring package on any import.

    Mutation check (red): add ``from monitoring.waste_monitor import WasteMonitor``
    back to ``models/data_classes.py`` -> this test reports that line and fails.
    """
    violations = sorted(
        v for path in MODELS_DIR.rglob("*.py") for v in _monitoring_imports_in(path)
    )
    assert not violations, (
        "models/ imports the monitoring package -- this is the inverted edge that "
        "closes the circular import. Depend on models.recording.EntityStatusRecorder "
        "and inject the concrete recorder from the composition root instead:\n  "
        + "\n  ".join(violations)
    )


def test_base_entity_does_not_construct_a_recorder():
    """An un-injected entity has no recorder; the base class must not build one.

    Mutation check (red): restore ``self.waste_monitor = WasteMonitor()`` in
    ``OperationalEntity.__init__`` -> ``waste_monitor`` is a WasteMonitor, not None.
    """
    entity = OperationalEntity()
    assert entity.waste_monitor is None


def test_injected_recorder_receives_status_transitions():
    """The recorder used during a failure transition is exactly the injected one.

    Mutation check (red): make ``__init__`` ignore the param and build its own
    recorder -> the spy records zero calls and the recorded-entity assertion fails.
    """

    class _SpyRecorder:
        """Satisfies EntityStatusRecorder; records the calls the domain layer makes."""

        def __init__(self):
            self.calls = []

        def record_entity_status(self, entity, timestamp):
            self.calls.append((entity, timestamp))

    spy = _SpyRecorder()
    # seed is irrelevant: probability 1.0 forces the OPERATIONAL -> FAILED edge,
    # which is the transition that records status.
    entity = OperationalEntity(seed=0, waste_monitor=spy)

    failed = entity.check_failure(current_time=5.0, failure_probability=1.0)

    assert failed is True
    assert spy.calls == [(entity, 5.0)], (
        "the failure transition must record through the injected recorder, "
        f"got calls={spy.calls!r}"
    )


def test_un_injected_entity_survives_a_transition_without_recording():
    """The ``waste_monitor`` guard must tolerate a None recorder (no crash).

    Mutation check (red): drop the ``and self.waste_monitor`` guard in
    ``check_failure`` -> calling it with no recorder raises AttributeError.
    """
    entity = OperationalEntity(seed=0)  # no recorder injected

    failed = entity.check_failure(current_time=5.0, failure_probability=1.0)

    assert failed is True  # transition still happened, it just was not recorded


def test_waste_monitor_satisfies_the_recorder_contract():
    """The production recorder must implement what the domain layer calls.

    Mutation check (red): rename ``WasteMonitor.record_entity_status`` -> the
    runtime-checkable Protocol no longer matches and this isinstance check fails.
    """
    from monitoring.waste_monitor import WasteMonitor

    assert isinstance(WasteMonitor(), EntityStatusRecorder)
