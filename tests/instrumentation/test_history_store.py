"""Recorder->store seam contract (clean-monitoring issue 09).

Issue 09 pulls the in-memory store -- the six history dicts + their getters --
out of ``WasteMonitor`` into ``instrumentation.history_store.HistoryStore``, so
the store HOLDS data, the recorder WRITES into it, and ``get_monitor_data`` READS
from it. The raw-vs-raw gate proves byte-stability of the move; these tests pin
the structural seam itself, so a future "inline the store back into the recorder"
regresses loudly here rather than silently passing the behavioral gates.

Issue 10 then reduces ``WasteMonitor`` to append-only: the empty-dict templates
that define each per-entity history shape move onto the store as ``ensure_*``
methods, so the recorder authors no schema -- the second block of tests pins that.

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

# The six schema authors the store owns (issue 10); the recorder only appends.
ENSURE_METHODS = (
    "ensure_generation",
    "ensure_collection",
    "ensure_processing",
    "ensure_event",
    "ensure_environmental",
    "ensure_entity_status",
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
        name = "OPERATIONAL"

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


# --- Issue 10: the store authors the per-entity schemas; the recorder appends only ---


def test_schema_authoring_lives_on_the_store_not_the_recorder():
    """The ``ensure_*`` schema authors resolve on the store; the recorder authors none.

    Issue 10 moves the empty-dict templates (and the ``demand.json`` product-types
    loader that one of them needs) off ``WasteMonitor`` onto ``HistoryStore``.

    Mutation check (red): re-inline a schema by restoring
    ``WasteMonitor._initialize_treatment_history`` / ``_get_product_types`` -> the
    recorder-authors-none assertions fail; or drop an ``ensure_*`` from the store ->
    the resolves-on-store assertion fails.
    """
    for method in ENSURE_METHODS:
        assert hasattr(HistoryStore, method), f"{method} missing from the store"
    assert not hasattr(WasteMonitor, "_initialize_treatment_history")
    assert not hasattr(WasteMonitor, "_get_product_types")


def test_ensure_generation_materializes_the_generation_schema():
    """``ensure_generation`` creates the per-generator entry with the exact key set.

    Cleanup #10 removed the generator cost series (``energy_costs``,
    ``operational_costs``, ``total_costs``): ``update_entity_costs`` was never
    called for generators, so every entry was a 0.0 stub.

    Mutation check (red): drop a key (e.g. ``"status"``) from the literal in
    ``ensure_generation``, or restore a removed cost series -> the key-set
    assertion fails.
    """
    store = HistoryStore()
    store.ensure_generation("gen-1")
    assert set(store.generation_history["gen-1"]) == {
        "timestamps", "volumes", "efficiency", "total_generated",
        "total_potential_generated", "storage_utilization", "status",
    }


def test_ensure_processing_materializes_nested_schema_from_product_types():
    """``ensure_processing`` builds the treatment schema with only read streams.

    VIZ-REVIEW T7 removed the write-only series (per-WasteType ``by_type``
    breakdowns, ``finished_goods_by_type``, ``products.total``, the constant
    ``products.quality`` and ``operational.energy_consumption``); the consumed
    ``products.by_type`` (avoided emissions, C11) is keyed, in order, by the
    demand product types the store loaded from ``demand.json``.

    Mutation check (red): drop ``"operational"`` from the literal, reorder the
    product-type comprehension, or restore a removed write-only series -> an
    assertion below fails.
    """
    store = HistoryStore()
    store.ensure_processing("t-1")
    history = store.processing_history["t-1"]
    assert set(history) == {
        "timestamps", "storage", "processed", "products", "operational", "status",
    }
    assert set(history["storage"]) == {
        "total", "utilization", "waste_utilization", "finished_goods_utilization",
    }
    assert set(history["processed"]) == {"total"}
    assert set(history["products"]) == {"by_type"}
    assert list(history["products"]["by_type"]) == store.product_types
    assert set(history["operational"]) == {
        "energy_costs", "processing_costs", "total_costs",
    }


def test_ensure_event_materializes_the_system_event_schema():
    """``ensure_event`` creates the event entry with only consumed series.

    VIZ-REVIEW T9: ``overflow_events`` (the redundant union of
    ``landfill_usage`` and ``storage_expansions``) is gone; the remaining
    volume/cost series all feed KPIs.

    Mutation check (red): restore ``overflow_events`` in the literal, or drop
    a consumed key -> the key-set assertion fails.
    """
    store = HistoryStore()
    store.ensure_event("system_events")
    assert set(store.event_history["system_events"]) == {
        "timestamps", "landfill_usage", "storage_expansions",
        "landfill_costs", "expansion_costs", "total_costs",
    }


def test_ensure_is_idempotent_and_does_not_clobber_samples():
    """A repeat ``ensure_*`` call preserves the entry the recorder has appended into.

    The recorder calls ``ensure_*`` every tick before appending, so the guard must
    be init-if-absent, not unconditional assignment.

    Mutation check (red): drop the ``if name not in ...`` guard in
    ``ensure_generation`` -> the second call resets the dict and the appended
    timestamp is lost, failing the assertion.
    """
    store = HistoryStore()
    store.ensure_generation("gen-1")
    store.generation_history["gen-1"]["timestamps"].append(7.0)
    store.ensure_generation("gen-1")
    assert store.generation_history["gen-1"]["timestamps"] == [7.0]
