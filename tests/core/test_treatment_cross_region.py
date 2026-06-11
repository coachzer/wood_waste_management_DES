"""Cross-region repositioning must not mutate collected_waste (ADR 0009).

``TreatmentOperator._collect_from_cross_region`` performs a collector-to-collector
repositioning move: it removes waste from a remote collector and routes it to a
local collector, from where treatment picks it up later via the normal local intake
path. The invariant is that ``collected_waste`` -- the dict that accumulates what
treatment has already received -- must NOT be mutated here; doing so would
double-count the repositioned volume in the waste-side mass balance.

ADR 0009 documents this as a real bug that was previously fixed. These tests pin
four aspects:

1. Double-count guard: ``collected_waste`` stays empty after the call regardless
   of what transport returns.
2. Return-value accounting: the method returns the unsatisfied remainder (request
   minus what transport supplied).
3. Nearest-three constraint: only the three geographically closest remote
   collectors are contacted; a same-region collector is never contacted.
4. Short-circuit on zero request: returning immediately without calling transport.
"""

from types import SimpleNamespace

import pytest

from core.treatment import TreatmentOperator
from models.enums import RegionType, WasteType


CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
PACKAGING = WasteType.WOODEN_PACKAGING_15_01_03


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------

def make_remote_collector(region_type, availability=True, name=None):
    """A collector stand-in for state.collectors.

    Uses real RegionType members so ``get_distance`` in the sort key works
    without monkeypatching.
    """
    return SimpleNamespace(
        region_type=region_type,
        availability=availability,
        name=name or region_type.value,
    )


def make_treatment_stub(
    home_region: RegionType,
    remote_collectors,
    transport_responses,
):
    """Build a minimal SimpleNamespace that satisfies ``_collect_from_cross_region``.

    ``transport_responses`` is a list of dicts (one per consecutive transport
    call) that ``_request_via_transport`` should return in order.

    Mirrors only the attributes the method reads: ``region_type``, ``state``,
    and ``_request_via_transport``.
    """
    call_log = []
    response_iter = iter(transport_responses)

    def fake_transport(self_ignored, collector, remaining, waste_types):
        call_log.append(collector)
        try:
            return next(response_iter)
        except StopIteration:
            return {}

    import types
    stub = SimpleNamespace(
        region_type=home_region,
        state=SimpleNamespace(collectors=remote_collectors),
        _call_log=call_log,
    )
    stub._request_via_transport = types.MethodType(fake_transport, stub)
    return stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cross_region_never_mutates_collected_waste():
    """Transport returning waste must NOT modify the collected_waste dict.

    This is the ADR 0009 double-count guard: repositioned waste reaches treatment
    via the later local intake path, so adding it to ``collected_waste`` here
    would count it twice.
    """
    home = RegionType.OSREDNJESLOVENSKA
    remote = make_remote_collector(RegionType.PODRAVSKA)

    stub = make_treatment_stub(
        home_region=home,
        remote_collectors=[remote],
        transport_responses=[{CONSTRUCTION: 10.0}],
    )

    collected_waste = {}
    TreatmentOperator._collect_from_cross_region(
        stub, 50.0, [CONSTRUCTION], collected_waste
    )

    assert collected_waste == {}, (
        "collected_waste must not be mutated by _collect_from_cross_region"
    )


def test_cross_region_return_is_unsatisfied_remainder():
    """The return value is the original request minus what transport supplied.

    Case 1: transport supplies a partial amount -- remainder > 0.
    Case 2: transport supplies everything -- remainder == 0.
    """
    home = RegionType.OSREDNJESLOVENSKA
    remote_a = make_remote_collector(RegionType.PODRAVSKA)
    remote_b = make_remote_collector(RegionType.GORENJSKA)

    # Case 1: two collectors, combined supply=60, request=100 -> remainder=40
    stub1 = make_treatment_stub(
        home_region=home,
        remote_collectors=[remote_a, remote_b],
        transport_responses=[{CONSTRUCTION: 40.0}, {CONSTRUCTION: 20.0}],
    )
    remainder1 = TreatmentOperator._collect_from_cross_region(
        stub1, 100.0, [CONSTRUCTION], {}
    )
    assert remainder1 == pytest.approx(40.0)

    # Case 2: first collector supplies everything, loop short-circuits -> remainder=0
    stub2 = make_treatment_stub(
        home_region=home,
        remote_collectors=[remote_a, remote_b],
        transport_responses=[{CONSTRUCTION: 100.0}],
    )
    remainder2 = TreatmentOperator._collect_from_cross_region(
        stub2, 100.0, [CONSTRUCTION], {}
    )
    assert remainder2 == pytest.approx(0.0)


def test_cross_region_consults_at_most_three_nearest_remote_collectors():
    """Only the three nearest remote collectors are contacted.

    A same-region collector in state.collectors must never be contacted
    regardless of its availability. Five remote collectors at increasing distance
    from OSREDNJESLOVENSKA are present; the method must visit only the three
    closest.
    """
    home = RegionType.OSREDNJESLOVENSKA

    # Ordered by ascending get_distance from OSREDNJESLOVENSKA:
    # GORENJSKA (~50 km) < GORISKA < SAVINJSKA < PODRAVSKA < KOROSKA
    # The exact ordering does not matter for the test -- we verify that
    # exactly 3 of the 5 remotes are contacted, and the same-region one is not.
    same_region = make_remote_collector(home, name="same-region-should-not-be-visited")
    remote1 = make_remote_collector(RegionType.GORENJSKA, name="r1")
    remote2 = make_remote_collector(RegionType.GORISKA, name="r2")
    remote3 = make_remote_collector(RegionType.SAVINJSKA, name="r3")
    remote4 = make_remote_collector(RegionType.PODRAVSKA, name="r4")
    remote5 = make_remote_collector(RegionType.KOROSKA, name="r5")

    # Transport returns zero so the loop never short-circuits on satisfaction
    stub = make_treatment_stub(
        home_region=home,
        remote_collectors=[same_region, remote1, remote2, remote3, remote4, remote5],
        transport_responses=[{}, {}, {}, {}, {}],
    )

    TreatmentOperator._collect_from_cross_region(
        stub, 100.0, [CONSTRUCTION], {}
    )

    visited_names = [c.name for c in stub._call_log]

    # Exactly 3 collectors contacted
    assert len(visited_names) == 3, (
        f"Expected 3 collectors contacted, got {len(visited_names)}: {visited_names}"
    )

    # Same-region collector never contacted
    assert "same-region-should-not-be-visited" not in visited_names, (
        "Same-region collector must not be contacted by _collect_from_cross_region"
    )


def test_zero_or_negative_request_short_circuits():
    """A zero or negative amount_to_collect returns 0.0 immediately.

    The early-exit guard ``if amount_to_collect <= 0: return 0.0`` is tested
    with a negative request (-5.0): without it the method would compute
    ``remaining = -5.0`` and return that negative value (no loop iteration
    occurs because ``remaining <= 0`` breaks immediately, but ``remaining``
    itself is -5.0). The mutation that removes the early return would return
    -5.0, not 0.0, making the assertion below fail.

    Transport is never called in either code path, so the call-log check is
    retained as a secondary sanity guard; it does not drive the non-vacuity.
    """
    home = RegionType.OSREDNJESLOVENSKA
    remote = make_remote_collector(RegionType.PODRAVSKA)

    stub = make_treatment_stub(
        home_region=home,
        remote_collectors=[remote],
        transport_responses=[{CONSTRUCTION: 999.0}],
    )

    # Negative request: the early exit must absorb it and return 0.0.
    result = TreatmentOperator._collect_from_cross_region(
        stub, -5.0, [CONSTRUCTION], {}
    )

    assert result == pytest.approx(0.0), (
        "A negative request must return 0.0, not the negative value itself"
    )
    assert stub._call_log == [], "Transport must not be called when request is non-positive"
