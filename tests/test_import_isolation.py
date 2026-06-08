"""Bootstrap-cycle guard for ``models.data_classes``.

Locks in the property that ``models.data_classes`` imports cleanly *in
isolation*, with no ``config`` submodule pre-imported. The hazard is a
``config <-> models.data_classes`` import cycle:

    models/data_classes.py  imports  config.constants
        -> running any config submodule runs config/__init__ first
        -> config/__init__ imports config.base_config
        -> config.base_config imports  models.data_classes  (FailureConfig)

When ``config`` is imported first the loop happens to resolve, but when
``models.data_classes`` is imported FIRST -- as a lone test method does -- the
back-edge reaches a half-initialized ``models.data_classes`` and raises
``ImportError: cannot import name 'FailureConfig'``. The historical workaround
was "always run the full suite" (so ``config`` is imported first); this guard
exists so that workaround can be retired.

It MUST run as a real subprocess with a clean interpreter: an in-process import
cannot reproduce the bug because by then ``config`` is already in ``sys.modules``.
The subprocess is a bare ``import`` (sub-second), so it is not marked ``slow``.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_in_clean_subprocess(module: str) -> subprocess.CompletedProcess:
    """Import ``module`` in a fresh interpreter with an empty module table."""
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_data_classes_imports_without_config_preimported():
    """``models.data_classes`` must import first, with no config in sys.modules.

    Guards the config<->data_classes bootstrap cycle: if a top-level
    ``from config...`` edge is reintroduced in data_classes, this subprocess
    import raises ImportError and the test goes red.
    """
    result = _import_in_clean_subprocess("models.data_classes")
    assert result.returncode == 0, (
        "importing models.data_classes in isolation failed -- the "
        "config<->data_classes bootstrap cycle is back\n"
        f"--- stderr ---\n{result.stderr}"
    )
