"""Road-circuity factor on great-circle distance (ADR 0015, cleanup #59).

``transportation_time`` was a half-wired scenario knob: carried through
``ScenarioConfig`` and ``UncertaintySet`` but never read. It is now a per-trip
road-circuity multiplier on the great-circle distance -- stochastic
(``Normal(mean, std)``, clamped >= 1.0) on collection trips, deterministic
mean on shared transport-manager repositioning. These tests pin the clamp,
the no-uncertainty-set fallback, and that ``_create_transport`` actually
applies the factor (a forgotten multiply would silently revert the knob to
half-wired).
"""

from types import SimpleNamespace

import pytest

from core.collector import CollectorCompany
from core.transport_manager import PointToPointTransport, TransportRequest
from models.enums import RegionType, WasteType


CIRCUITY_SET = SimpleNamespace(transportation_time=(1.35, 0.1))


class FixedRng:
    """rng stub returning a preset normal draw, recording the call args."""

    def __init__(self, value):
        self.value = value
        self.calls = []

    def normal(self, mean, std):
        self.calls.append((mean, std))
        return self.value


def sample(uncertainty_set, rng):
    fake = SimpleNamespace(uncertainty_set=uncertainty_set, rng=rng)
    return CollectorCompany._sample_transport_circuity(fake)


def test_sample_clamps_draws_below_one():
    assert sample(CIRCUITY_SET, FixedRng(0.7)) == 1.0


def test_sample_passes_draws_above_one_through():
    assert sample(CIRCUITY_SET, FixedRng(1.5)) == 1.5


def test_sample_draws_from_scenario_mean_and_std():
    rng = FixedRng(1.2)
    sample(CIRCUITY_SET, rng)
    assert rng.calls == [(1.35, 0.1)]


def test_sample_without_uncertainty_set_is_identity_and_skips_rng():
    # rng=None: any draw attempt would raise, proving the early return.
    assert sample(None, None) == 1.0


def test_mean_circuity_without_uncertainty_set_is_identity():
    assert PointToPointTransport()._mean_transport_circuity() == 1.0


def test_mean_circuity_uses_deterministic_scenario_mean():
    manager = PointToPointTransport(uncertainty_set=CIRCUITY_SET)
    assert manager._mean_transport_circuity() == 1.35


def test_mean_circuity_clamped_to_one():
    manager = PointToPointTransport(
        uncertainty_set=SimpleNamespace(transportation_time=(0.8, 0.1))
    )
    assert manager._mean_transport_circuity() == 1.0


def _repositioning_times(uncertainty_set, vehicle_region):
    """(pickup_time, main-leg travel time) of one repositioning trip.

    With the vehicle parked at the origin the pickup leg is zero and
    arrival - pickup isolates the main leg; with the vehicle elsewhere,
    pickup_time isolates the pickup leg (current_time is 0).
    """
    state = SimpleNamespace(
        collectors=[],
        track_transport_flow=lambda **kwargs: None,
    )
    manager = PointToPointTransport(state=state, uncertainty_set=uncertainty_set)
    vehicle = SimpleNamespace(
        current_region=vehicle_region,
        in_transit=False,
        destination=None,
        estimated_arrival=None,
        current_load=0.0,
        current_load_by_type={},
    )
    request = TransportRequest(
        origin=RegionType.POMURSKA,
        destination=RegionType.PODRAVSKA,
        waste_type=WasteType.CONSTRUCTION_WOOD_17_02_01,
        volume=10.0,
        request_time=0.0,
        requester_id="collector-1",
    )
    transport = manager._create_transport(
        request, {"vehicle": vehicle, "collector": None}, current_time=0.0
    )
    return (
        transport["pickup_time"],
        transport["arrival_time"] - transport["pickup_time"],
    )


def test_create_transport_scales_travel_time_by_mean_circuity():
    _, baseline = _repositioning_times(None, RegionType.POMURSKA)
    _, with_circuity = _repositioning_times(CIRCUITY_SET, RegionType.POMURSKA)
    assert baseline > 0.0
    # approx: the code multiplies circuity into the distance before the
    # speed divisions, so exact float equality with baseline * 1.35 differs
    # in the last ulp.
    assert with_circuity == pytest.approx(baseline * 1.35, rel=1e-12)


def test_create_transport_scales_pickup_leg_by_mean_circuity():
    baseline, _ = _repositioning_times(None, RegionType.SAVINJSKA)
    with_circuity, _ = _repositioning_times(CIRCUITY_SET, RegionType.SAVINJSKA)
    assert baseline > 0.0
    assert with_circuity == pytest.approx(baseline * 1.35, rel=1e-12)
