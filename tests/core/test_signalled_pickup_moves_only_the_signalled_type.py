"""A kanban signal moves only the waste type it names (ADR 0028)."""
import simpy

from tests.core.factories import make_collector, make_generator_site
from models.enums import InventoryPolicy, WasteType

FIRST_IN_DICT = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05
SIGNALLED = WasteType.CONSTRUCTION_WOOD_17_02_01


def _pickup(ledger_waste_monitor, **request):
    """Run one pickup inside the first tick from a generator holding 500 m3 of each type."""
    env = simpy.Environment()
    collector = make_collector(
        env,
        ledger_waste_monitor,
        waste_types=[FIRST_IN_DICT, SIGNALLED],
        collection_capacity=1_000.0,
        collection_frequency=1,
        inventory_policy=InventoryPolicy.PULL,
    )
    generator = make_generator_site({FIRST_IN_DICT: 500.0, SIGNALLED: 500.0})
    collector.collect_from_generator(generator, **request)
    env.run(until=0.9)
    stored = {waste_type: volume for waste_type, volume in collector.collection_center.current_storage.items() if volume}
    return stored, generator


def test_signalled_pickup_takes_only_the_signalled_type(ledger_waste_monitor):
    stored, generator = _pickup(ledger_waste_monitor, requested_volume=300.0, waste_type=SIGNALLED)

    assert stored == {SIGNALLED: 300.0}
    assert generator.waste_streams[FIRST_IN_DICT].volume == 500.0


def test_unsignalled_pickup_still_takes_any_stream(ledger_waste_monitor):
    stored, _ = _pickup(ledger_waste_monitor, requested_volume=800.0)

    assert sum(stored.values()) == 800.0
    assert set(stored) == {FIRST_IN_DICT, SIGNALLED}
