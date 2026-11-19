"""KanbanManager reads never mutate the bus; expiry is applied at read time."""
from config.constants import KANBAN_SIGNAL_MAX_AGE_DAYS
from core.kanban_manager import KanbanManager
from models.enums import WasteType

WASTE = WasteType.CONSTRUCTION_WOOD_17_02_01


def _bus_with_one_signal_at_day_zero():
    kanban_manager = KanbanManager()
    kanban_manager.add_signal(waste_type=WASTE, timestamp=0.0, volume=5, source_id="g", source_type="generator")
    return kanban_manager


def test_reading_after_expiry_hides_the_signal_but_leaves_the_bus_untouched():
    kanban_manager = _bus_with_one_signal_at_day_zero()
    expired_time = KANBAN_SIGNAL_MAX_AGE_DAYS + 1.0

    assert kanban_manager.get_signals(expired_time) == []
    assert len(kanban_manager.signals) == 1


def test_a_signal_raised_on_day_t_is_still_visible_to_a_reader_one_tick_later():
    kanban_manager = _bus_with_one_signal_at_day_zero()

    assert len(kanban_manager.get_signals(KANBAN_SIGNAL_MAX_AGE_DAYS)) == 1


def test_adding_a_signal_prunes_expired_signals_and_their_acknowledgments():
    kanban_manager = _bus_with_one_signal_at_day_zero()
    old_id = kanban_manager.signals[0]["id"]
    kanban_manager.acknowledge_signal(old_id)
    later_time = KANBAN_SIGNAL_MAX_AGE_DAYS + 1.0

    kanban_manager.add_signal(waste_type=WASTE, timestamp=later_time, volume=5, source_id="g", source_type="generator")

    assert [signal["timestamp"] for signal in kanban_manager.signals] == [later_time]
    assert old_id not in kanban_manager.acknowledged_signals
