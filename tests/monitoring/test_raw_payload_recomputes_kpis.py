"""A persisted raw sidecar holds everything extract_kpis reads.

The sidecar exists so a new KPI can be computed without re-running. It used to
drop final_summary and storage_capacities, so service levels, consumed volume and
residence times recomputed from a sidecar silently came out None or zero.
"""
import json

import pytest

from analysis._kpi_shared import _flatten_namespaces
from analysis.baseline_aggregate import extract_kpis
from config.base_config import get_scenario_config
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy
from persistence.serialization import build_raw_payload, jsonify


def test_kpis_recomputed_from_the_raw_sidecar_match_the_live_run():
    manager = SimulationManager(seed=3)
    manager.initialize_entities(get_scenario_config("Baseline"), InventoryPolicy.PULL, StockStrategy.REORDER_50)
    manager.setup_processes(raise_on_violation=False)
    manager.run_simulation()
    monitor_data = manager.get_monitor_data()

    reloaded = json.loads(json.dumps(jsonify(build_raw_payload(monitor_data))))

    live = _flatten_namespaces(json.loads(json.dumps(jsonify(extract_kpis(monitor_data)))))
    recomputed = _flatten_namespaces(json.loads(json.dumps(jsonify(extract_kpis(reloaded)))))

    assert recomputed.keys() == live.keys()

    # Summing string-keyed dicts can reorder float additions, so values may
    # differ in the last digit.
    assert recomputed == pytest.approx(live, rel=1e-12, nan_ok=True)
