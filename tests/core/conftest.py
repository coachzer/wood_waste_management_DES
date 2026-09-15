"""Shared fixtures for the core test suite."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def noop_waste_monitor():
    """A no-op WasteMonitor stand-in so tracking calls have somewhere to go."""
    return SimpleNamespace(
        track_expansion=lambda **kwargs: None,
        record_landfill=lambda **kwargs: None,
        record_emission=lambda **kwargs: None,
    )


@pytest.fixture
def ledger_waste_monitor():
    """A real WasteMonitor, for tests that read back the landfill ledger."""
    from instrumentation.waste_monitor import WasteMonitor

    return WasteMonitor()
