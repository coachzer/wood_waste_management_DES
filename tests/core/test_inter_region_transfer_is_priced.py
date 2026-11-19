"""A completed inter-region transfer is charged like a collection trip over road km (ADR 0034, 0038)."""
from types import SimpleNamespace

import pytest

from config.constants import (
    COLLECTION_COST_PER_KM_PER_M3,
    KILOGRAMS_PER_TONNE,
    ROAD_CIRCUITY_FACTOR,
    TRANSPORT_EMISSIONS_PER_TON_KM,
    WASTE_DENSITIES,
)
from core.collector import CollectorCompany
from models.distances import get_distance
from models.enums import RegionType, WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


class RecordingMonitor:
    def __init__(self):
        self.costs, self.emissions = [], []

    def update_entity_costs(self, entity_name, transport_cost, **_):
        self.costs.append((entity_name, transport_cost))

    def record_emission(self, entity_name, kgco2e, **_):
        self.emissions.append((entity_name, kgco2e))


def _collector(name, region_type, monitor):
    collector = SimpleNamespace(
        name=name, region_type=region_type, facility_type="collector", transport_cost=50.0,
        waste_monitor=monitor, env=SimpleNamespace(now=3.0),
        collection_center=SimpleNamespace(current_storage={WASTE: 0.0}),
    )
    collector.charge_trip = (
        lambda load, distance: CollectorCompany.charge_trip(collector, load, distance)
    )
    return collector


def test_completed_transfer_charges_the_vehicle_owner():
    """Mutation check (red): drop the charge in _handle_completed_transport."""
    monitor = RecordingMonitor()
    owner = _collector("col_owner", RegionType.PODRAVSKA, monitor)
    destination = _collector("col_destination", RegionType.OSREDNJESLOVENSKA, monitor)
    owner.state = SimpleNamespace(collectors=[owner, destination])
    transport = {
        "vehicle": SimpleNamespace(current_region=RegionType.OSREDNJESLOVENSKA),
        "collector": owner, "waste_type": WASTE, "volume": 40.0,
        "origin": RegionType.GORENJSKA, "destination": RegionType.OSREDNJESLOVENSKA,
    }

    CollectorCompany._handle_completed_transport(owner, transport)

    distance = get_distance(RegionType.GORENJSKA, RegionType.OSREDNJESLOVENSKA) * ROAD_CIRCUITY_FACTOR
    assert destination.collection_center.current_storage[WASTE] == 40.0
    assert monitor.costs == [("col_owner", pytest.approx(50.0 + distance * COLLECTION_COST_PER_KM_PER_M3 * 40.0))]
    tonnes = 40.0 * WASTE_DENSITIES[WASTE] / KILOGRAMS_PER_TONNE
    assert monitor.emissions == [("col_owner", pytest.approx(tonnes * distance * TRANSPORT_EMISSIONS_PER_TON_KM))]
