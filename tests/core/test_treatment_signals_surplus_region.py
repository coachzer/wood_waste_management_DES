"""A PULL operator short of local stock also signals the region holding the most (ADR 0033)."""
from types import SimpleNamespace

from models.enums import RegionType, WasteType
from tests.core.factories import (
    EMPTY_PULL_OPERATOR_ORDER_M3,
    run_empty_pull_operator,
    signal_recording_collector,
    signals_addressed_to,
)

CONSTRUCTION = WasteType.CONSTRUCTION_WOOD_17_02_01
LOCAL_REGION = RegionType.PODRAVSKA


def _generator(region, stock):
    return SimpleNamespace(region_type=region, waste_streams={CONSTRUCTION: SimpleNamespace(volume=stock)})


def _signals_after_order(waste_monitor, local_generator_stock):
    """Signal volumes per collector after one tick that orders EMPTY_PULL_OPERATOR_ORDER_M3 (100)."""
    small_region, large_region = [region for region in RegionType if region != LOCAL_REGION][:2]
    collectors = {
        "local": signal_recording_collector(LOCAL_REGION, {}),
        "small": signal_recording_collector(small_region, {}),
        "large": signal_recording_collector(large_region, {}),
    }
    run_empty_pull_operator(
        waste_monitor,
        collectors.values(),
        generators=[
            _generator(LOCAL_REGION, local_generator_stock),
            _generator(small_region, 50.0),
            _generator(large_region, 400.0),
        ],
    )
    return {
        name: [signal["volume"] for signal in signals_addressed_to(collector)]
        for name, collector in collectors.items()
    }


def test_deficit_goes_to_the_region_with_the_largest_generator_stock(noop_waste_monitor):
    """Mutation check (red): drop the surplus-region signal."""
    assert _signals_after_order(noop_waste_monitor, local_generator_stock=30.0) == {
        "local": [EMPTY_PULL_OPERATOR_ORDER_M3], "small": [], "large": [70.0],
    }


def test_no_remote_signal_when_local_stock_covers_the_order(noop_waste_monitor):
    """Mutation check (red): signal the surplus region regardless of local stock."""
    assert _signals_after_order(noop_waste_monitor, local_generator_stock=150.0) == {
        "local": [EMPTY_PULL_OPERATOR_ORDER_M3], "small": [], "large": [],
    }
