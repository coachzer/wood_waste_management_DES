# Prime the import graph in the order main.py uses so importing the monitoring
# package under pytest does not trip the known monitoring/__init__ circular
# import (see CLAUDE.md). Importing config.base_config first pulls
# models.data_classes -> monitoring.waste_monitor in cleanly, before the
# monitoring package __init__ runs.
import config.base_config  # noqa: F401

import pytest


def pytest_addoption(parser):
    """Register --run-slow so opt-in heavyweight tests stay out of the default run."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.slow (e.g. the cross-process determinism guard)",
    )


def pytest_configure(config):
    """Declare the slow marker so using it does not warn."""
    config.addinivalue_line(
        "markers",
        "slow: opt-in test that spawns subprocesses or is otherwise heavyweight; run with --run-slow",
    )


def pytest_collection_modifyitems(config, items):
    """Skip slow-marked tests unless --run-slow was passed, keeping `pytest tests/ -q` fast."""
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="needs --run-slow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
