"""Fast static guard against unsorted set iteration on ordered-work paths.

CLAUDE.md / HANDOFF.md landmine: iterating a ``set`` of ``WasteType``/
``OutputType`` members breaks cross-process reproducibility, because enum
members hash by ``id()`` (uncontrolled by ``PYTHONHASHSEED``), so set order
follows per-process memory layout. The fix is always ``sorted(<set>, key=lambda
e: e.value)`` -- a List, never a re-wrapped set.

``test_determinism.py`` proves this end-to-end, but only as a ``slow`` opt-in
(two subprocess baseline runs). This guard runs in the default suite in
milliseconds: it flags the *idiom* before it can ship. The safe pattern wraps
the set in ``sorted(...)``, where the set is an ARGUMENT to the call -- never the
direct ``.iter`` of a loop or comprehension. So a set literal, set
comprehension, or ``set(...)`` call appearing AS the iterable being looped over
is the hazard; a sorted-wrapped set is not, because its ``.iter`` is the
``sorted`` call.

A genuinely order-insensitive direct iteration (rare) should be made a List or
``sorted`` set to satisfy this guard, which keeps ordered-work paths honest.
"""
import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Simulation-affecting source trees. Tests and scratch infra are excluded. The
# former ``monitoring`` tree was split by the clean-monitoring refactor into the
# instrumentation/persistence/analysis/visualization spaces, all scanned here.
SCANNED_DIRS = (
    "core",
    "models",
    "instrumentation",
    "persistence",
    "analysis",
    "visualization",
)


def _is_direct_set_iterable(node: ast.AST) -> bool:
    """True if ``node`` is a set being iterated directly (the hazard idiom)."""
    if isinstance(node, (ast.Set, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "set":
            return True
    return False


def _iter_python_files():
    for sub in SCANNED_DIRS:
        yield from (REPO_ROOT / sub).rglob("*.py")


def _violations_in(path: Path) -> list[str]:
    """Return 'file:line' for every set iterated directly by a loop/comprehension."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT).as_posix()
    found: list[str] = []
    for node in ast.walk(tree):
        iterables: list[ast.AST] = []
        if isinstance(node, ast.For):
            iterables.append(node.iter)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            iterables.extend(generator.iter for generator in node.generators)
        for iterable in iterables:
            if _is_direct_set_iterable(iterable):
                found.append(f"{rel}:{iterable.lineno}")
    return found


def test_no_unsorted_set_iteration_on_sim_paths():
    violations = sorted(
        violation for path in _iter_python_files() for violation in _violations_in(path)
    )
    assert not violations, (
        "set iterated directly (not wrapped in sorted(..., key=lambda e: e.value)) "
        "-- breaks cross-process reproducibility if the set holds enums. Wrap in "
        f"sorted() and pass an ordered List:\n  " + "\n  ".join(violations)
    )
