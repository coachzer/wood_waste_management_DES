"""One remote drain trip per (operator, collector, tick) across the per-type requests (ADR 0042).

``trigger_collection`` requests each ordered type separately (ADR 0026). Charging each per-type
drain as its own trip billed the fixed trip cost once per waste type for what is one pickup.
"""
from types import SimpleNamespace

import simpy

from models.distances import get_distance
from models.enums import RegionType, WasteType
from models.state import SimulationState
from tests.core.test_operating_clock import _treatment

EARLY_TYPE = WasteType.CONSTRUCTION_WOOD_17_02_01
LATE_TYPE = WasteType.NON_HAZARDOUS_WOOD_20_01_38


def _remote_collector(name, region_type, charges):
    stock = {EARLY_TYPE: 1_000.0, LATE_TYPE: 1_000.0}

    def provide_waste_for_treatment(requested_amount, needed_types, treatment_name=None):
        drained = {}
        for waste_type in needed_types:
            take = min(stock[waste_type], requested_amount)
            stock[waste_type] -= take
            requested_amount -= take
            if take > 0:
                drained[waste_type] = take
        return drained

    return SimpleNamespace(
        name=name, region_type=region_type, is_operational=True,
        provide_waste_for_treatment=provide_waste_for_treatment,
        # An empty center offers nothing for transfer, so every volume comes through the fallback drain.
        transferable_volume=lambda waste_type: 0.0,
        charge_trip=lambda load, distance: charges.append((name, dict(load), distance)),
    )


def _operator_with(collectors):
    state = SimulationState()
    operator = _treatment(simpy.Environment(), state=state)
    operator._waste_storage = dict.fromkeys(WasteType, 0.0)
    state.collectors = collectors
    return operator


def test_two_types_drained_from_one_remote_collector_pay_one_trip():
    charges = []
    remote_region = RegionType.POMURSKA
    operator = _operator_with([_remote_collector("col_remote", remote_region, charges)])
    assert operator.region_type != remote_region

    operator.trigger_collection({EARLY_TYPE: 100.0, LATE_TYPE: 40.0})

    assert charges == [("col_remote", {EARLY_TYPE: 100.0, LATE_TYPE: 40.0},
                        get_distance(remote_region, operator.region_type))]


def test_each_remote_collector_drained_pays_its_own_trip():
    charges = []
    first = _remote_collector("col_first", RegionType.POMURSKA, charges)
    second = _remote_collector("col_second", RegionType.KOROSKA, charges)
    operator = _operator_with([first, second])

    operator.trigger_collection({EARLY_TYPE: 1_500.0})

    assert [(name, load) for name, load, _ in charges] == [
        ("col_first", {EARLY_TYPE: 1_000.0}), ("col_second", {EARLY_TYPE: 500.0})]
