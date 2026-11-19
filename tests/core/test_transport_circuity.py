"""Road-circuity factor on great-circle distance (ADR 0015, cleanup #59).

The scenario's ``transportation_time`` is a per-trip road-circuity multiplier
on the great-circle distance -- stochastic (``Normal(mean, std)``, clamped
>= 1.0) on collection trips, deterministic mean on shared transport-manager
repositioning. These tests pin the clamp and that a processed transfer
actually applies the factor (a forgotten multiply would silently revert the
knob to half-wired).
"""

from types import SimpleNamespace

import simpy

import pytest

from core.collector import CollectorCompany
from core.transport_manager import PointToPointTransport, TransportRequest
from models.data_classes import Vehicle
from models.enums import EntityStatus, RegionType, WasteType


CIRCUITY_SCENARIO = SimpleNamespace(transportation_time=(1.35, 0.1))
WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


class FixedRng:
    """rng stub returning a preset normal draw, recording the call args."""

    def __init__(self, value):
        self.value = value
        self.calls = []

    def normal(self, mean, std):
        self.calls.append((mean, std))
        return self.value


def sample(scenario, rng):
    fake = SimpleNamespace(scenario=scenario, rng=rng)
    return CollectorCompany._sample_transport_circuity(fake)


def test_sample_clamps_draws_below_one():
    assert sample(CIRCUITY_SCENARIO, FixedRng(0.7)) == 1.0


def test_sample_passes_draws_above_one_through():
    assert sample(CIRCUITY_SCENARIO, FixedRng(1.5)) == 1.5


def test_sample_draws_from_scenario_mean_and_std():
    rng = FixedRng(1.2)
    sample(CIRCUITY_SCENARIO, rng)
    assert rng.calls == [(1.35, 0.1)]


def _repositioning_times(road_circuity_mean, vehicle_region):
    """(pickup_time, main-leg travel time) of one Pomurska -> Podravska transfer.

    The only vehicle is parked in ``vehicle_region``. With it at the origin the
    pickup leg is zero and arrival - pickup isolates the main leg; with it
    elsewhere, pickup_time isolates the pickup leg (current_time is 0).
    """
    origin = SimpleNamespace(
        name="collector-1", region_type=RegionType.POMURSKA, vehicles=[],
        status=EntityStatus.OPERATIONAL,
        collection_center=SimpleNamespace(current_storage={WASTE: 10.0}),
    )
    owner = origin if vehicle_region == RegionType.POMURSKA else SimpleNamespace(
        name="collector-owner", region_type=vehicle_region, vehicles=[],
        status=EntityStatus.OPERATIONAL, collection_center=SimpleNamespace(current_storage={}),
    )
    owner.vehicles.append(Vehicle(id="v1", capacity=50.0, current_region=vehicle_region))
    state = SimpleNamespace(
        collectors=[origin] if owner is origin else [origin, owner],
        track_transport_flow=lambda **kwargs: None,
    )
    manager = PointToPointTransport(state=state, road_circuity_mean=road_circuity_mean, env=simpy.Environment())
    manager.request_transport(TransportRequest(
        origin=RegionType.POMURSKA, destination=RegionType.PODRAVSKA, waste_type=WASTE,
        volume=10.0, request_time=0.0, requester_id="collector-1",
    ))
    [transport] = manager.process_requests(current_time=0.0)
    return transport["pickup_time"], transport["arrival_time"] - transport["pickup_time"]


@pytest.mark.parametrize("vehicle_region", [RegionType.POMURSKA, RegionType.SAVINJSKA])
def test_mean_circuity_below_one_is_clamped_to_great_circle(vehicle_region):
    assert _repositioning_times(0.8, vehicle_region) == _repositioning_times(1.0, vehicle_region)


def test_transfer_scales_travel_time_by_mean_circuity():
    _, baseline = _repositioning_times(1.0, RegionType.POMURSKA)
    _, with_circuity = _repositioning_times(1.35, RegionType.POMURSKA)
    assert baseline > 0.0
    # approx: the code multiplies circuity into the distance before the
    # speed divisions, so exact float equality with baseline * 1.35 differs
    # in the last ulp.
    assert with_circuity == pytest.approx(baseline * 1.35, rel=1e-12)


def test_transfer_scales_pickup_leg_by_mean_circuity():
    baseline, _ = _repositioning_times(1.0, RegionType.SAVINJSKA)
    with_circuity, _ = _repositioning_times(1.35, RegionType.SAVINJSKA)
    assert baseline > 0.0
    assert with_circuity == pytest.approx(baseline * 1.35, rel=1e-12)
