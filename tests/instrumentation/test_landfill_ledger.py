"""The landfill and emission ledgers on HistoryStore are the single record.

A landfill used to be written three ways per event -- an entity attribute
nobody read, a per-name counter on ``SimulationState`` the mass-balance
monitor read, and an entity-less monitor bucket ``extract_kpis`` read -- so the
invariant and the KPI could silently diverge. Now ``handle_storage_event``
writes once, to ``HistoryStore.record_landfill``, and both readers go through
the same module-level readers. These tests pin the ledger semantics and the
reader identity.

Each assertion is mutation-verified non-vacuous -- see the per-test docstrings.
"""
import json

import pytest

from instrumentation.history_store import (
    EMISSION_KINDS,
    HistoryStore,
    landfilled_volume_by_entity,
    total_emissions_kgco2e,
    total_landfill_cost,
    total_landfilled_volume,
)
from models.enums import InventoryPolicy, StockStrategy, WasteType

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
PAPER = WasteType.PAPER_PACKAGING_15_01_01


# --- record_landfill --------------------------------------------------------


def test_record_landfill_accumulates_volume_and_cost_per_entity():
    """Two events on one entity and one on another sum per name; the volume is
    the total over the composition, the cost is taken as given.

    Mutation check (red): make ``record_landfill`` append ``len(composition)``
    instead of ``sum(composition.values())``, or key the entry by a constant
    -> the per-entity totals below fail.
    """
    store = HistoryStore()
    store.record_landfill("col-1", {SAWDUST: 30.0, PAPER: 12.5}, cost=10.0, timestamp=1.0)
    store.record_landfill("col-1", {SAWDUST: 7.5}, cost=2.0, timestamp=5.0)
    store.record_landfill("col-2", {PAPER: 4.0}, cost=1.0, timestamp=5.0)

    assert store.landfilled_volume_by_entity() == {"col-1": 50.0, "col-2": 4.0}
    assert store.total_landfilled_volume() == 54.0
    assert total_landfill_cost(store.landfill_history) == 13.0
    assert store.landfill_history["col-1"]["timestamps"] == [1.0, 5.0]


def test_record_landfill_snapshots_the_composition():
    """The per-type split (ADR 0013) is copied, so a caller reusing its dict
    after the call cannot rewrite the ledger.

    Mutation check (red): store ``composition`` itself instead of
    ``dict(composition)`` -> the later mutation shows up in the ledger.
    """
    store = HistoryStore()
    composition = {SAWDUST: 10.0}
    store.record_landfill("col-1", composition, cost=0.0, timestamp=0.0)
    composition[SAWDUST] = 999.0

    assert store.landfill_history["col-1"]["compositions"] == [{SAWDUST: 10.0}]


def test_landfill_readers_agree_on_the_serialized_copy():
    """The module-level readers give the same totals on the JSON round-tripped
    ledger as the live store does, so a post-hoc ``extract_kpis`` over
    ``raw_NNN.json`` cannot drift from the in-process value.

    Mutation check (red): make ``total_landfilled_volume`` read ``"costs"``
    -> the per-entity totals become the costs (10.0, 1.0).
    """
    from persistence.serialization import jsonify

    store = HistoryStore()
    store.record_landfill("col-1", {SAWDUST: 30.0, PAPER: 12.5}, cost=10.0, timestamp=1.0)
    store.record_landfill("col-2", {PAPER: 4.0}, cost=1.0, timestamp=5.0)

    round_tripped = json.loads(json.dumps(jsonify(store.landfill_history)))

    expected_by_entity = {"col-1": 42.5, "col-2": 4.0}
    assert store.landfilled_volume_by_entity() == expected_by_entity
    assert landfilled_volume_by_entity(round_tripped) == expected_by_entity
    assert store.total_landfilled_volume() == total_landfilled_volume(round_tripped) == 46.5
    assert total_landfill_cost(store.landfill_history) == total_landfill_cost(round_tripped) == 11.0


# --- record_emission --------------------------------------------------------


def test_record_emission_accrues_into_one_slot_per_timestamp():
    """Same-timestamp emissions of any kind share one slot; a later timestamp
    opens a new one. ``total_impact`` is the per-slot sum over kinds and the
    reader sums the slots.

    Mutation check (red): drop the ``timestamp > last`` guard (always open a
    slot) -> the slot count becomes 3; or stop adding into ``total_impact`` ->
    the reader returns 0.
    """
    store = HistoryStore()
    store.record_emission("col-1", "transport_emissions", 10.0, timestamp=1.0)
    store.record_emission("col-1", "landfill_emissions", 5.0, timestamp=1.0)
    store.record_emission("col-1", "transport_emissions", 20.0, timestamp=2.0)

    entry = store.environmental_history["col-1"]
    assert entry["timestamps"] == [1.0, 2.0]
    assert entry["transport_emissions"] == [10.0, 20.0]
    assert entry["landfill_emissions"] == [5.0, 0.0]
    assert entry["total_impact"] == [15.0, 20.0]
    assert total_emissions_kgco2e(store.environmental_history) == 35.0


def test_record_emission_rejects_an_unknown_kind():
    """A kind outside ``EMISSION_KINDS`` is a programming error and raises
    rather than being logged and dropped (the old recorder's behaviour).

    Mutation check (red): remove the membership check -> KeyError or a silent
    write instead of ValueError.
    """
    store = HistoryStore()
    assert "biogenic" not in EMISSION_KINDS
    with pytest.raises(ValueError):
        store.record_emission("col-1", "biogenic", 1.0, timestamp=0.0)
    assert store.environmental_history == {}


# --- The invariant: one ledger, two readers, one number --------------------


FORCED_OVERFLOW_COLLECTION_CENTER_CAPACITY_M3 = 200.0


def test_mass_balance_and_kpi_read_the_same_landfill_ledger():
    """On a real run, the raw-waste discard term the mass-balance monitor closed
    its identities with equals ``extract_kpis``' ``landfill_volume_m3`` -- both
    in process and after the raw payload is serialized and reloaded.

    The run itself is the first half of the assertion: ``run_simulation``
    executes the armed waste-side invariants (``raise_on_violation=True``), so a
    ledger that under-reports trips ``MassBalanceViolation`` before the
    comparison is reached. The ``> 0`` guard keeps the equality from closing
    trivially on a run that never landfilled. Since ADR 0023 no Baseline combo
    landfills, so the run shrinks every collection center to
    ``FORCED_OVERFLOW_COLLECTION_CENTER_CAPACITY_M3`` to force overflow.

    Mutation checks (red): (a) in ``extract_kpis`` read ``landfill_volume``
    from ``event_history`` again -> 0 != ledger total; (b) make
    ``EntityRegistry.landfilled_by_entity`` return ``{}`` -> the waste invariant
    raises inside ``run_simulation``; (c) skip ``record_landfill`` in
    ``handle_storage_event`` -> same as (b).
    """
    from analysis.baseline_aggregate import extract_kpis
    from config.base_config import get_scenario_config
    from core.simulation_manager import SimulationManager
    from persistence.serialization import build_raw_payload, jsonify

    manager = SimulationManager(seed=7)
    manager.initialize_entities(
        get_scenario_config("Baseline"), InventoryPolicy.PULL, StockStrategy.ON_DEMAND
    )
    for collector in manager.state.collectors:
        collector.collection_center.waste_storage_capacity = FORCED_OVERFLOW_COLLECTION_CENTER_CAPACITY_M3
    manager.setup_processes(raise_on_violation=True)
    manager.run_simulation()

    ledger_total = sum(
        manager.mass_balance_monitor.registry.landfilled_by_entity().values()
    )
    assert ledger_total > 0.0

    monitor_data = manager.get_monitor_data()
    assert extract_kpis(monitor_data)["landfill_volume_m3"] == ledger_total

    reloaded = json.loads(json.dumps(jsonify(build_raw_payload(monitor_data))))
    assert extract_kpis(reloaded)["landfill_volume_m3"] == ledger_total
