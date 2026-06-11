"""Waste-side inventory holding cost accrual (all three echelons).

Reintroduces the generator cost series removed by cleanup #10 (9b238a7), this
time with a real cost source: each daily monitor sample accrues
``stored volume x WASTE_HOLDING_COST_PER_M3_PER_DAY`` into a per-entity
``holding_costs`` series, at generators, collectors, and treatment operators
alike. The series is kept separate from the existing ``total_costs`` /
``operational.total_costs`` series so the transport and processing KPI
components stay pure; the KPI layer sums it into its own ``holding_cost``
component of ``total_system_cost``.

Each assertion is mutation-verified non-vacuous -- see the per-test docstrings.
"""
from config.constants import WASTE_HOLDING_COST_PER_M3_PER_DAY
from instrumentation.waste_monitor import WasteMonitor


class _Status:
    name = "OPERATIONAL"


class _Stream:
    def __init__(self, volume):
        self.volume = volume


def _generator_stub(current_storage):
    class _Generator:
        name = "gen-1"
        status = _Status()
        waste_streams = {}
        total_generated = {}
        total_potential_generated = {}
        efficiency = 1.0
        waste_storage_capacity = 1000.0

    generator = _Generator()
    generator.current_storage = current_storage
    return generator


def test_track_generation_accrues_daily_holding_cost_on_stored_waste():
    """Each generation sample appends ``current_storage x rate`` to ``holding_costs``.

    The monitor samples every entity once per simulated day
    (``monitor_system_process`` yields ``timeout(1)``), so a per-sample accrual
    of ``stored m3 x rate`` is exactly one day of holding cost.

    Mutation check (red): drop the accrual append (or append 0.0) in
    ``track_generation`` -> the value assertion fails; accrue against
    ``waste_storage_capacity`` instead of ``current_storage`` -> 1000 x rate
    != 240 x rate and the assertion fails.
    """
    monitor = WasteMonitor()
    generator = _generator_stub(current_storage=240.0)

    monitor.track_generation(generator, timestamp=3.0)

    history = monitor.store.generation_history["gen-1"]
    assert history["holding_costs"] == [240.0 * WASTE_HOLDING_COST_PER_M3_PER_DAY]


def test_track_collection_accrues_daily_holding_cost_on_collection_center_storage():
    """Each collection sample accrues on the collection center's stored waste,
    in a ``holding_costs`` series separate from the transport ``total_costs``.

    Mutation check (red): drop the accrual append -> KeyError/empty-list
    failure; accrue into ``total_costs`` instead -> the holding_costs equality
    fails and the total_costs purity assertion fails too (transport KPI would
    be polluted).
    """

    class _CollectionCenter:
        current_storage = {"a": 70.0, "b": 30.0}
        waste_storage_capacity = 500.0

    class _Collector:
        name = "col-1"
        status = _Status()
        collected_waste = {}
        efficiency = 1.0
        collection_center = _CollectionCenter()
        last_collection_cost = 12.5

    monitor = WasteMonitor()
    monitor.track_collection(_Collector(), timestamp=3.0)

    history = monitor.store.collection_history["col-1"]
    assert history["holding_costs"] == [100.0 * WASTE_HOLDING_COST_PER_M3_PER_DAY]
    # Holding cost must not leak into the series the transport KPI sums.
    assert history["total_costs"] == [0.0]


def test_track_processing_accrues_once_per_day_under_the_same_timestamp_guard():
    """Treatment accrues on its waste storage; a same-timestamp re-entry does
    not double-accrue.

    ``track_processing`` is called both by the daily monitor process and from
    the treatment operator's own loop (``core/treatment.py``); the existing
    ``timestamp > last`` guard dedupes rows. Holding cost must sit inside that
    guard or a busy operator would accrue more holding cost per day than an
    idle one with identical storage.

    Mutation check (red): drop the accrual -> first assertion fails; move the
    accrual outside the guard -> the second (single-entry) assertion fails.
    """

    class _FinishedGoods:
        capacity = {"mdf": 100.0}
        current_storage = {"mdf": 10.0}

    class _Treatment:
        name = "t-1"
        status = _Status()
        current_storage = 80.0
        storage_utilization = 8.0
        waste_storage_capacity = 1000.0
        finished_goods = _FinishedGoods()
        processed_volumes = {}
        product_volumes = {}

    monitor = WasteMonitor()
    treatment = _Treatment()
    monitor.track_processing(treatment, timestamp=5.0)
    monitor.track_processing(treatment, timestamp=5.0)  # same-tick re-entry

    history = monitor.store.processing_history["t-1"]
    assert history["operational"]["holding_costs"] == [
        80.0 * WASTE_HOLDING_COST_PER_M3_PER_DAY
    ]
    # Processing KPI purity: holding cost stays out of operational total_costs.
    assert history["operational"]["total_costs"] == [0.0]


def test_holding_cost_kpi_sums_all_three_echelons_into_total_system_cost():
    """``extract_kpis`` reports ``holding_cost`` summed over generators,
    collectors, and treatment operators, and folds it into
    ``total_system_cost`` alongside the three existing components.

    Mutation check (red): drop an echelon from the holding sum -> 60.0 becomes
    a partial sum and the first assertion fails; leave ``holding_cost`` out of
    ``total_system_cost`` -> the closure assertion fails; drop it from
    ``_SUMMARY_METRICS`` -> the wiring assertion fails (the KPI would never
    reach summary.csv).
    """
    from analysis.baseline_aggregate import _SUMMARY_METRICS, extract_kpis

    monitor_data = {
        "generation_history": {
            "gen-1": {"holding_costs": [10.0, 20.0]},
        },
        "collection_history": {
            "col-1": {"holding_costs": [5.0, 5.0], "total_costs": [100.0, 0.0]},
        },
        "processing_history": {
            "t-1": {
                "operational": {
                    "holding_costs": [15.0, 5.0],
                    "total_costs": [200.0, 0.0],
                }
            },
        },
    }
    kpis = extract_kpis(monitor_data)
    assert kpis["holding_cost"] == 60.0
    # total_system_cost closes over transport + processing + overflow + holding.
    assert kpis["total_system_cost"] == 100.0 + 200.0 + 0.0 + 60.0
    assert "holding_cost" in _SUMMARY_METRICS
