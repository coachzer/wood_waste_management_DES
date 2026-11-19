"""The domain layer (``models/``) never imports the recording layer (``instrumentation``).

Importing the concrete ``WasteMonitor`` from ``models/`` closes a circular
import. Entities receive their recorder from the composition root instead.
"""
import ast
from pathlib import Path

from models.data_classes import OperationalEntity

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "models"

# The recording layer the domain must never import: the ``instrumentation`` space the
# concrete recorders moved to (issue 07). Importing it concretely from ``models/``
# re-closes the inverted circular import.
RECORDING_LAYER_ROOTS = ("instrumentation",)


def _names_recording_root(name: str) -> bool:
    """True if a dotted import name targets a recording-layer package or submodule."""
    return any(name == root or name.startswith(root + ".") for root in RECORDING_LAYER_ROOTS)


def _recording_layer_imports_in(path: Path) -> list[str]:
    """Return 'file:line' for every import of a recording-layer package in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT).as_posix()
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _names_recording_root(alias.name):
                    found.append(f"{rel}:{node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # level>0 is a relative import within models/, which can never reach a
            # top-level recording-layer package, so only absolute imports matter.
            if node.level == 0 and _names_recording_root(module):
                found.append(f"{rel}:{node.lineno}")
    return found


def test_models_layer_does_not_import_the_recording_layer():
    """The domain layer must not name a recording-layer package on any import.

    Mutation check (red): add ``from instrumentation.waste_monitor import WasteMonitor``
    to ``models/data_classes.py`` -> this test reports that line and fails, so the
    guarded ``instrumentation`` root is real, not vacuous.
    """
    violations = sorted(
        v for path in MODELS_DIR.rglob("*.py") for v in _recording_layer_imports_in(path)
    )
    assert not violations, (
        "models/ imports the recording layer (instrumentation/) -- this is "
        "the inverted edge that closes the circular import. Inject the "
        "recorder from the composition root instead:\n  " + "\n  ".join(violations)
    )


def test_base_entity_does_not_construct_a_recorder():
    """An un-injected entity has no recorder; the base class must not build one.

    Mutation check (red): restore ``self.waste_monitor = WasteMonitor()`` in
    ``OperationalEntity.__init__`` -> ``waste_monitor`` is a WasteMonitor, not None.
    """
    entity = OperationalEntity()
    assert entity.waste_monitor is None
