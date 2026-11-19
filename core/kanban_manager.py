from typing import List, Dict, Any

from config.constants import KANBAN_SIGNAL_MAX_AGE_DAYS

class KanbanManager:
    def __init__(self):
        self.signals: List[Dict[str, Any]] = []
        self.max_signal_age = KANBAN_SIGNAL_MAX_AGE_DAYS
        self.acknowledged_signals = set()

    def add_signal(self, waste_type, timestamp, volume=0, source_id=None, source_type=None, target_region=None):
        self.clean_old_signals(timestamp)
        signal_id = f"{source_id}_{waste_type}_{timestamp}_{target_region}"

        if signal_id in self.acknowledged_signals or any(signal['id'] == signal_id for signal in self.signals):
            return
        self.signals.append({
            'id': signal_id,
            'waste_type': waste_type,
            'timestamp': timestamp,
            'volume': volume,
            'source_id': source_id,
            "source_type": source_type,
            'target_region': target_region,
        })

    def acknowledge_signal(self, signal_id):
        """Mark signal as processed"""
        self.acknowledged_signals.add(signal_id)

    def clean_old_signals(self, current_time):
        """Remove signals older than max_signal_age and prune stale acknowledgments"""
        self.signals = [
            signal for signal in self.signals
            if current_time - signal['timestamp'] <= self.max_signal_age
        ]
        remaining_ids = {signal['id'] for signal in self.signals}
        self.acknowledged_signals &= remaining_ids

    def get_signals(self, current_time=None):
        """Get non-acknowledged signals, and only unexpired ones when ``current_time`` is given.

        Reading never mutates the bus. Expired signals are pruned when a new signal is added.
        """
        return [
            signal for signal in self.signals
            if signal['id'] not in self.acknowledged_signals
            and (current_time is None or current_time - signal['timestamp'] <= self.max_signal_age)
        ]
