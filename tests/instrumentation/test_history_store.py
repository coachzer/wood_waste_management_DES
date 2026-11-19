"""HistoryStore holds the run's history; WasteMonitor writes into it.

The store also authors each per-entity history shape (the ``ensure_*``
methods), so ``get_monitor_data`` and the KPI readers see the same keys
whichever recorder path created the entry.
"""
from instrumentation.history_store import HistoryStore
from instrumentation.waste_monitor import WasteMonitor


def test_recorder_writes_status_into_the_store():
    """A recorded status transition lands in the store, not a recorder-local dict.

    Mutation check (red): point ``record_entity_status`` at a ``self``-owned dict
    instead of ``self.store.entity_status_history`` -> the store stays empty and
    the membership assertion fails.
    """

    class _Status:
        name = "OPERATIONAL"

    class WasteGenerator:
        facility_type = "generator"
        name = "gen-1"
        status = _Status()

    monitor = WasteMonitor()
    monitor.record_entity_status(WasteGenerator(), timestamp=4.0)

    generators = monitor.store.entity_status_history["generators"]
    assert "gen-1" in generators
    assert generators["gen-1"]["timestamps"] == [4.0]
    assert generators["gen-1"]["status"] == ["OPERATIONAL"]


# --- Issue 10: the store authors the per-entity schemas; the recorder appends only ---


def test_ensure_generation_materializes_the_generation_schema():
    """``ensure_generation`` creates the per-generator entry with the exact key set.

    Cleanup #10 removed the generator cost series (``energy_costs``,
    ``operational_costs``, ``total_costs``): ``update_entity_costs`` was never
    called for generators, so every entry was a 0.0 stub. The sole cost series
    since reintroduced is ``holding_costs``, fed by the daily holding-cost
    accrual in ``track_generation`` (see ``test_holding_cost.py``).

    Mutation check (red): drop a key (e.g. ``"status"``) from the literal in
    ``ensure_generation``, or restore a removed zero-stub cost series -> the
    key-set assertion fails.
    """
    store = HistoryStore()
    store.ensure_generation("gen-1")
    assert set(store.generation_history["gen-1"]) == {
        "timestamps", "volumes", "efficiency", "total_generated",
        "total_potential_generated", "total_uncollected", "total_outlet", "storage_utilization", "status",
        "holding_costs",
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
        "energy_costs", "processing_costs", "total_costs", "holding_costs",
    }


def test_ensure_event_materializes_the_system_event_schema():
    """``ensure_event`` creates the event entry with only consumed series.

    VIZ-REVIEW T9 dropped ``overflow_events``; the landfill columns
    (``landfill_usage`` / ``landfill_costs``) then moved to the per-entity
    landfill ledger (``record_landfill``), so the stream carries expansions
    only. ``total_costs`` stays for the event-cost timeline readers.

    Mutation check (red): restore a landfill column in the literal, or drop
    a consumed key -> the key-set assertion fails.
    """
    store = HistoryStore()
    store.ensure_event("system_events")
    assert set(store.event_history["system_events"]) == {
        "timestamps", "storage_expansions", "expansion_costs", "total_costs",
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
