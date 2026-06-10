"""Shared fixtures for the core test suite."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def noop_waste_monitor():
    """A no-op WasteMonitor stand-in so tracking calls have somewhere to go."""
    return SimpleNamespace(
        track_event=lambda **kwargs: None,
        track_environmental_impact=lambda **kwargs: None,
    )
