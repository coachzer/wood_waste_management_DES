"""Package-init contract for the monitoring refactor (clean-monitoring issue 03).

Issue 02 broke the ``models -> monitoring`` edge; issue 03 removes the now-dead
re-exports from ``monitoring/__init__.py``. The re-exports were not merely unused
(no caller does ``from monitoring import X``): because the package ``__init__``
eagerly imported ``waste_monitor``, ``scenario_comparison`` and
``mfa_visualization``, *any* ``import monitoring.<submodule>`` dragged in the
heavy plotly-backed visualization stack and re-armed the import cycle that forced
the "run by file path, not ``-m``" workaround.

These tests pin three failure modes:
  1. submodule imports creeping back into the package ``__init__`` (static AST guard);
  2. importing the package eagerly loading a heavy submodule (behavioral, clean subprocess);
  3. an analysis ``-m`` entry point failing to import after the space move (behavioral).

The behavioral checks run in a fresh interpreter so an unrelated earlier import
in this test session cannot mask a regression. Each assertion is mutation-verified
non-vacuous -- see the per-test docstrings for the exact mutation that turns it red.
"""
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "monitoring" / "__init__.py"

# The visualization module is the canary: it pulls in plotly and is the heaviest
# thing the old re-exports forced to load. If importing the bare package loads it,
# the eager-import regression is back.
HEAVY_CANARY = "monitoring.mfa_visualization"

# The four post-hoc analysis entry points are the ``-m`` targets. They moved to the
# ``analysis`` space (issue 05); importing each in a clean process is the regression
# guard that every relative import inside ``analysis/`` still resolves. The monitoring
# import cycle itself is prevented elsewhere -- see test 3's docstring.
DASH_M_MODULES = (
    "analysis.paired_comparison",
    "analysis.stochastic_dominance",
    "analysis.pareto",
    "analysis.baseline_aggregate",
)


def test_package_init_imports_no_submodules():
    """``monitoring/__init__`` must not import any ``monitoring`` submodule.

    Mutation check (red): re-add ``from .waste_monitor import WasteMonitor`` to
    ``monitoring/__init__.py`` -> this test reports that line and fails.
    """
    tree = ast.parse(INIT_PATH.read_text(encoding="utf-8"), filename=str(INIT_PATH))
    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # A relative import (``from .x``) or an absolute ``monitoring.x`` both
            # name a submodule and re-arm eager loading.
            if node.level > 0 or (node.module or "").startswith("monitoring"):
                offending.append(f"line {node.lineno}: from {'.' * node.level}{node.module or ''}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("monitoring."):
                    offending.append(f"line {node.lineno}: import {alias.name}")
    assert not offending, (
        "monitoring/__init__.py imports a submodule -- this re-arms eager loading "
        "of the heavy visualization stack and the import cycle. Keep __init__ free "
        "of submodule imports:\n  " + "\n  ".join(offending)
    )


def test_importing_package_does_not_load_heavy_submodule():
    """``import monitoring`` must not transitively load the plotly-backed canary.

    Mutation check (red): restore ``from .mfa_visualization import ...`` in
    ``monitoring/__init__.py`` -> the canary appears in ``sys.modules`` and this
    subprocess prints LOADED, failing the assertion.
    """
    probe = (
        "import sys; import monitoring; "
        f"print('LOADED' if {HEAVY_CANARY!r} in sys.modules else 'ABSENT')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ABSENT", (
        f"importing the monitoring package eagerly loaded {HEAVY_CANARY}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_dash_m_entry_points_import_without_cycle():
    """Each analysis ``-m`` entry point must import cleanly in a fresh process.

    These are the ``python -m analysis.<module>`` targets. Importing each in a clean
    interpreter proves its now-relative (issue 05) intra-``analysis`` imports all
    resolve and no import error -- cycle or otherwise -- bites.

    Mutation check (red): change a sibling import in ``analysis/baseline_aggregate.py``
    back to the pre-move ``from monitoring.bullwhip import ...`` -> ``monitoring.bullwhip``
    no longer exists, so ``import analysis.baseline_aggregate`` raises ModuleNotFoundError,
    the subprocess exits non-zero, and this test fails.

    The monitoring import cycle is double-guarded elsewhere, so it is not re-checked
    here: ``test_package_init_imports_no_submodules`` (no eager submodule imports in
    ``monitoring/__init__``) and ``tests/test_recorder_injection.py`` (the domain layer
    does not import ``monitoring``) -- restoring either half of the cycle turns one of
    those red.
    """
    for module in DASH_M_MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"importing {module} failed in a clean process:\n{result.stderr}"
        )
