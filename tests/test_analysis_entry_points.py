"""The ``analysis`` package's ``-m`` entry points import cleanly in a fresh process.

The post-hoc analysis modules are run as ``python -m analysis.<module>``. After the
clean-monitoring space move (issue 05) their intra-package imports became relative;
importing each in a clean interpreter is the regression guard that every relative
import inside ``analysis/`` still resolves and no import error -- cycle or otherwise --
bites. The check runs in a fresh interpreter so an unrelated earlier import in this
test session cannot mask a regression.

(The husk ``monitoring/__init__`` package this file once also guarded was deleted
once it held nothing; the import-inversion contract is pinned by
``tests/test_recorder_injection.py``.)
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The four post-hoc analysis entry points are the ``-m`` targets. They moved to the
# ``analysis`` space (issue 05); importing each in a clean process is the regression
# guard that every relative import inside ``analysis/`` still resolves.
DASH_M_MODULES = (
    "analysis.paired_comparison",
    "analysis.stochastic_dominance",
    "analysis.pareto",
    "analysis.baseline_aggregate",
)


def test_dash_m_entry_points_import_without_cycle():
    """Each analysis ``-m`` entry point must import cleanly in a fresh process.

    Mutation check (red): change a sibling import in ``analysis/baseline_aggregate.py``
    to a non-existent module (e.g. the pre-move ``from monitoring.bullwhip import ...``)
    -> ``import analysis.baseline_aggregate`` raises ModuleNotFoundError, the subprocess
    exits non-zero, and this test fails.
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
