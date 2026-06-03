"""System-wide outbound-vehicle iterator and per-waste-type vehicle load (C2).

``Vehicle.current_load_by_type`` breaks the scalar ``current_load`` down by waste
type so the waste-side mass-balance invariant (C3) can sum waste in transit.
``SimulationState.iter_outbound_vehicles`` is the single seam that finds every
in-transit vehicle across all collectors' fleets.
"""

from types import SimpleNamespace

from models.data_classes import Vehicle
from models.enums import RegionType, WasteType
from models.state import SimulationState


def make_vehicle(vehicle_id, in_transit, load_by_type):
    """A Vehicle whose scalar load is kept consistent with its per-type breakdown."""
    return Vehicle(
        id=vehicle_id,
        capacity=1000.0,
        current_region=RegionType.PODRAVSKA,
        in_transit=in_transit,
        current_load=sum(load_by_type.values()),
        current_load_by_type=dict(load_by_type),
    )


def collector_with(vehicles):
    """A collector stand-in exposing only the .vehicles fleet the iterator reads."""
    return SimpleNamespace(vehicles=vehicles)


def test_vehicle_load_by_type_defaults_empty():
    vehicle = Vehicle(id="v0", capacity=100.0, current_region=RegionType.PODRAVSKA)
    assert vehicle.current_load_by_type == {}
    assert vehicle.current_load == 0.0


def test_iter_outbound_yields_only_in_transit_vehicles():
    wt = sorted(WasteType, key=lambda e: e.value)[0]
    moving = make_vehicle("moving", in_transit=True, load_by_type={wt: 12.0})
    idle = make_vehicle("idle", in_transit=False, load_by_type={})
    state = SimulationState()
    state.collectors = [collector_with([moving, idle])]

    outbound = list(state.iter_outbound_vehicles())

    assert [v.id for v in outbound] == ["moving"]


def test_iter_outbound_spans_all_collectors_and_breakdown_sums_to_scalar():
    types = sorted(WasteType, key=lambda e: e.value)
    one = make_vehicle("one", in_transit=True, load_by_type={types[0]: 5.0})
    two = make_vehicle("two", in_transit=True, load_by_type={types[0]: 3.0, types[1]: 7.0})
    state = SimulationState()
    state.collectors = [collector_with([one]), collector_with([two])]

    outbound = list(state.iter_outbound_vehicles())

    assert {v.id for v in outbound} == {"one", "two"}
    for vehicle in outbound:
        assert sum(vehicle.current_load_by_type.values()) == vehicle.current_load


def test_iter_outbound_empty_when_no_vehicles_moving():
    state = SimulationState()
    state.collectors = [collector_with([make_vehicle("v", in_transit=False, load_by_type={})])]
    assert list(state.iter_outbound_vehicles()) == []
