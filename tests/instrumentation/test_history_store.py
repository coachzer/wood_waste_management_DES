"""Recorder->store seam contract (clean-monitoring issue 09).

Issue 09 pulls the in-memory store -- the six history dicts + their getters --
out of ``WasteMonitor`` into ``instrumentation.history_store.HistoryStore``, so
the store HOLDS data, the recorder WRITES into it, and ``get_monitor_data`` READS
from it. The raw-vs-raw gate proves byte-stability of the move; these tests pin
the structural seam itself, so a future "inline the store back into the recorder"
regresses loudly here rather than silently passing the behavioral gates.

Each assertion is mutation-verified non-vacuous -- see the per-test docstrings.
Run in full-suite context: single-test isolation can ImportError on the
``config`` <-> ``models.data_classes`` bootstrap cycle (HANDOFF.md landmine 3).
"""
from instrumentation.history_store import HistoryStore
from instrumentation.waste_monitor import WasteMonitor

# The six raw history dicts the store owns and the recorder writes into.
HISTORY_GETTERS = (
    "get_generation_history",
    "get_collection_history",
    "get_processing_history",
    "get_environmental_history",
    "get_event_history",
    "get_entity_status_history",
)


def test_recorder_owns_a_history_store():
    """``WasteMonitor.store`` is the dedicated ``HistoryStore``, not the recorder itself.

    Mutation check (red): revert ``__init__`` to set ``self.generation_history = {}``
    (etc.) on the recorder instead of ``self.store = HistoryStore()`` -> ``.store``
    is missing and ``getattr`` below raises / the isinstance fails.
    """
    monitor = WasteMonitor()
    assert isinstance(monitor.store, HistoryStore)


def test_getters_live_on_the_store_not_the_recorder():
    """The six history getters resolve on the store, and no longer on the recorder.

    Mutation check (red): leave the ``get_*_history`` properties defined on
    ``WasteMonitor`` -> the second assertion (absent-on-recorder) fails.
    """
    monitor = WasteMonitor()
    for getter in HISTORY_GETTERS:
        assert hasattr(monitor.store, getter), f"{getter} missing from the store"
        assert not hasattr(type(monitor), getter), f"{getter} still on the recorder"


def test_recorder_writes_status_into_the_store():
    """A recorded status transition lands in the store, not a recorder-local dict.

    ``record_entity_status`` maps an entity by ``type(entity).__name__``, so the
    stub class is named ``WasteGenerator`` to route into the ``generators`` bucket.

    Mutation check (red): point ``record_entity_status`` at a ``self``-owned dict
    instead of ``self.store.entity_status_history`` -> the store stays empty and
    the membership assertion fails.
    """

    class _Status:
        value = "OPERATIONAL"

    class WasteGenerator:
        """Named to match the recorder's type-name -> 'generators' mapping."""

        name = "gen-1"
        status = _Status()

    monitor = WasteMonitor()
    monitor.record_entity_status(WasteGenerator(), timestamp=4.0)

    generators = monitor.store.entity_status_history["generators"]
    assert "gen-1" in generators
    assert generators["gen-1"]["timestamps"] == [4.0]
    assert generators["gen-1"]["status"] == ["OPERATIONAL"]
