"""A fallback drain from another region is charged as a loaded trip; a local drain is not (ADR 0037)."""
import types
from types import SimpleNamespace

from core.treatment import TreatmentOperator
from models.distances import get_distance
from models.enums import RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01
HOME = RegionType.OSREDNJESLOVENSKA


def _collector(region_type, stock, charges):
    def provide(requested_amount, needed_types, treatment_name=None):
        taken = min(stock, requested_amount)
        return {WASTE: taken} if taken else {}
    return SimpleNamespace(
        region_type=region_type,
        is_operational=True,
        provide_waste_for_treatment=provide,
        charge_trip=lambda load, distance: charges.append((region_type, load, distance)),
    )


def test_only_the_remote_drain_is_charged_over_its_distance():
    """Mutation check (red): skip the charge, or charge local drains too."""
    charges = []
    local = _collector(HOME, 30.0, charges)
    remote = _collector(RegionType.GORENJSKA, 500.0, charges)
    operator = SimpleNamespace(name="proc_home", region_type=HOME, state=SimpleNamespace(collectors=[local, remote]))
    operator._drain_collectors = types.MethodType(TreatmentOperator._drain_collectors, operator)
    collected_waste = {}

    remaining = TreatmentOperator._collect_with_fallback(operator, 100.0, [WASTE], collected_waste)

    assert remaining == 0.0
    assert collected_waste == {WASTE: 100.0}
    assert charges == [(RegionType.GORENJSKA, {WASTE: 70.0}, get_distance(RegionType.GORENJSKA, HOME))]
